import type { Jurisdiction } from "@plumbline/ts-client";

/** The four jurisdictions, always in this order (DESIGN.md: Content). */
export const JURISDICTIONS = [
  { id: "dubai", code: "AE-DU", name: "Dubai" },
  { id: "spain", code: "ES", name: "Spain" },
  { id: "colombia", code: "CO", name: "Colombia" },
  { id: "florida", code: "US-FL", name: "Florida" },
] as const satisfies readonly { id: Jurisdiction; code: string; name: string }[];

export type JurisdictionInfo = (typeof JURISDICTIONS)[number];
