import fs from "node:fs";
import path from "node:path";

import { z } from "zod";

import { HEADLINE_CONFIG } from "./evals";
import { evalsDir } from "./evals-files";
import { JURISDICTION_IDS } from "./jurisdictions";
import type { ReplayFile, ReplayItem } from "./replay";

// Read at build time only, by /replay.json. Each line is checked here, so the page that reads
// the file in the browser needs no schema library; a line that does not fit fails the build.

const jurisdiction = z.enum(JURISDICTION_IDS);

const citation = z.object({
  n: z.number().int().min(1),
  chunk_id: z.string().min(1),
  ref: z.object({
    jurisdiction,
    law: z.string(),
    article: z.string(),
    paragraph: z.string().nullable().default(null),
    edition: z.string(),
  }),
  label: z.string().min(1),
  quote: z.string().min(1),
  gloss: z.string().nullable().default(null),
  language: z.enum(["en", "es"]),
  verified: z.boolean(),
  page: z.number().int().min(1).nullable().default(null),
});

const item = z.object({
  item_id: z.string(),
  question: z.string().min(1),
  jurisdictions: z.array(jurisdiction),
  as_of: z.iso.date().nullable().default(null),
  answer: z.object({
    text: z.string(),
    status: z.enum(["answered", "partial", "abstained"]),
    citations: z.array(citation).default([]),
    jurisdictions: z.array(jurisdiction).default([]),
    as_of: z.iso.date().nullable().default(null),
    confidence: z.number().min(0).max(1).nullable().default(null),
    abstain_reason: z.string().nullable().default(null),
    invalid_citations: z.number().int().min(0).default(0),
  }),
  trace: z.object({
    model: z.string(),
    route: z.string(),
    timings_ms: z.record(z.string(), z.number()).default({}),
    input_tokens: z.number().int().min(0).default(0),
    output_tokens: z.number().int().min(0).default(0),
    cost_usd: z.number().min(0).default(0),
    cached: z.boolean().default(false),
  }),
});

/** The default configuration's stored dev answers, or the first configuration that has any;
 * an empty file when none has been stored. */
export function loadReplay(dir: string = evalsDir()): ReplayFile {
  const replayDir = path.join(dir, "replay");
  const configs = fs.existsSync(replayDir)
    ? fs
        .readdirSync(replayDir)
        .filter((name) => fs.existsSync(path.join(replayDir, name, "dev.jsonl")))
    : [];
  const config = configs.includes(HEADLINE_CONFIG) ? HEADLINE_CONFIG : configs.sort()[0];
  if (!config) return { config: null, config_hash: null, items: [] };
  const file = path.join(replayDir, config, "dev.jsonl");
  const items: ReplayItem[] = fs
    .readFileSync(file, "utf8")
    .split("\n")
    .flatMap((line, index) => {
      if (line.trim() === "") return [];
      const parsed = item.safeParse(JSON.parse(line));
      if (!parsed.success) {
        throw new Error(
          `${file}:${index + 1} does not fit the replay's schema: ${parsed.error.message}`,
        );
      }
      return [parsed.data];
    });
  const hash = (() => {
    const results = path.join(dir, "results", config, "dev.json");
    if (!fs.existsSync(results)) return null;
    const run: unknown = JSON.parse(fs.readFileSync(results, "utf8"));
    return typeof run === "object" &&
      run !== null &&
      "config_hash" in run &&
      typeof run.config_hash === "string"
      ? run.config_hash
      : null;
  })();
  return { config, config_hash: hash, items };
}
