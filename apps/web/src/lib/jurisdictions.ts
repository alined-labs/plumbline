import type { Jurisdiction } from "@plumbline/ts-client";

// Keyed by the API's identifiers, so a jurisdiction added to the API fails to compile here
// until it has a code and a name.
const INFO = {
  dubai: { code: "AE-DU", name: "Dubai" },
  spain: { code: "ES", name: "Spain" },
  colombia: { code: "CO", name: "Colombia" },
  florida: { code: "US-FL", name: "Florida" },
} as const satisfies Record<Jurisdiction, { code: string; name: string }>;

/** The four jurisdictions, always in this order (DESIGN.md: Content). */
export const JURISDICTION_IDS = ["dubai", "spain", "colombia", "florida"] as const;

export type JurisdictionInfo = { id: Jurisdiction; code: string; name: string };

export function jurisdictionInfo(id: Jurisdiction): JurisdictionInfo {
  return { id, ...INFO[id] };
}

export const JURISDICTIONS: JurisdictionInfo[] = JURISDICTION_IDS.map(jurisdictionInfo);
