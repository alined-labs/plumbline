import { z } from "zod";

import manifest from "../../../../data/corpus/manifest.json";

import { JURISDICTION_IDS, JURISDICTIONS, type JurisdictionInfo } from "./jurisdictions";

// Each law's last-updated date comes from Lane B's corpus manifest, read at build time,
// until the API serves it. Only the fields the footer shows are parsed; the rest of a row
// (hash, licence, path) stays with the API's own validator.
const sourceSchema = z.object({
  id: z.string(),
  title: z.string(),
  jurisdiction: z.enum(JURISDICTION_IDS),
  edition: z.string(),
  consolidated_on: z.iso.date().nullish(),
  retrieved_on: z.iso.date(),
});

const manifestSchema = z.object({ sources: z.array(sourceSchema) });

export type LawEdition = {
  id: string;
  title: string;
  edition: string;
  /** The consolidation date when the source has one, otherwise the day it was retrieved. */
  updatedOn: string;
};

export type JurisdictionLaws = JurisdictionInfo & { laws: LawEdition[] };

/** The indexed laws per jurisdiction, in the fixed jurisdiction order. */
export function lawsByJurisdiction(input: unknown = manifest): JurisdictionLaws[] {
  const { sources } = manifestSchema.parse(input);
  return JURISDICTIONS.map((jurisdiction) => ({
    ...jurisdiction,
    laws: sources
      .filter((source) => source.jurisdiction === jurisdiction.id)
      .map((source) => ({
        id: source.id,
        title: source.title,
        edition: source.edition,
        updatedOn: source.consolidated_on ?? source.retrieved_on,
      })),
  }));
}
