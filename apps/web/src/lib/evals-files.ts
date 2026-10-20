import fs from "node:fs";
import path from "node:path";

import {
  agreementSchema,
  byConfigOrder,
  evalRunSchema,
  METRICS,
  type Agreement,
  type EvalRun,
  type MetricName,
} from "./evals";

// Read at build time only, by the evaluation page (a server component in the static export).
// The repository's evals/ folder is two levels above the app, where `next build` runs;
// PLUMBLINE_EVALS_DIR points a preview build at another folder, such as the test fixtures.

export type EvalsData = {
  /** The dev split's runs, one per configuration, in the ablation plan's order. */
  runs: EvalRun[];
  agreement: Agreement | null;
  /** The CI gate's thresholds per metric, from evals/baseline.json. */
  thresholds: Partial<Record<MetricName, number>>;
};

export function evalsDir(): string {
  return process.env.PLUMBLINE_EVALS_DIR ?? path.join(process.cwd(), "..", "..", "evals");
}

function readJson(file: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    throw new Error(`${file}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function parse<T>(file: string, schema: { parse: (input: unknown) => T }): T {
  try {
    return schema.parse(readJson(file));
  } catch (error) {
    throw new Error(`${file} does not fit the page's schema: ${String(error)}`);
  }
}

/** Every evals/results/<config>/dev.json, the judge's agreement table and the gate's
 * thresholds. A missing file is a section still to come; a malformed one fails the build. */
export function loadEvals(dir: string = evalsDir()): EvalsData {
  const resultsDir = path.join(dir, "results");
  const runs = fs.existsSync(resultsDir)
    ? fs
        .readdirSync(resultsDir, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .map((entry) => path.join(resultsDir, entry.name, "dev.json"))
        .filter((file) => fs.existsSync(file))
        .map((file) => parse(file, evalRunSchema))
        .sort(byConfigOrder)
    : [];

  const agreementFile = path.join(dir, "calibration", "agreement.json");
  const agreement = fs.existsSync(agreementFile) ? parse(agreementFile, agreementSchema) : null;

  return { runs, agreement, thresholds: thresholdsFrom(path.join(dir, "baseline.json")) };
}

/** The gate's numeric thresholds for metrics the page knows. Lane A owns the file's shape;
 * anything else in it (a justification, a version) is left alone. */
function thresholdsFrom(file: string): EvalsData["thresholds"] {
  if (!fs.existsSync(file)) return {};
  const input = readJson(file);
  if (typeof input !== "object" || input === null) return {};
  const record = input as Record<string, unknown>;
  const source =
    typeof record.thresholds === "object" && record.thresholds !== null
      ? (record.thresholds as Record<string, unknown>)
      : record;
  const thresholds: EvalsData["thresholds"] = {};
  for (const name of Object.keys(METRICS) as MetricName[]) {
    const value = source[name];
    if (typeof value === "number") thresholds[name] = value;
  }
  return thresholds;
}
