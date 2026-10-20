import { JURISDICTION_IDS, type JurisdictionInfo, jurisdictionInfo } from "./jurisdictions";

// The ten invented leases in data/leases (Lane B's), offered on the lease page while real
// uploads are off: every name, address and amount in them is fictitious, so they can go to a
// model without redaction.

/** Real uploads wait for redaction (Presidio, Lane P's P2). "on" brings the dropzone back. */
export const LEASE_UPLOADS = process.env.NEXT_PUBLIC_LEASE_UPLOADS === "on";

export type SampleLease = {
  id: string;
  /** What tells this lease from the others ("Miami apartment"); the title when none is given. */
  place: string;
  title: string;
  jurisdiction: JurisdictionInfo;
  /** ISO date. */
  signedOn: string;
};

const JURISDICTION_NAMES: Record<string, (typeof JURISDICTION_IDS)[number]> = {
  dubai: "dubai",
  spain: "spain",
  colombia: "colombia",
  florida: "florida",
};

/** A lease's file name and where the page fetches it from (a static file in the export). */
export function leasePath(id: string): `/leases/${string}.md` {
  return `/leases/${id}.md`;
}

/** The header every lease opens with (data/leases/README.md: Format): a "# " title, then
 * "- Lease id:", "- Jurisdiction:" and "- Signed on:" lines. Null when one is missing, so a
 * lease that strays from the format is left out rather than shown wrong. */
export function parseLeaseHeader(text: string): SampleLease | null {
  const title = /^# (.+)$/m.exec(text)?.[1]?.trim();
  const id = /^- Lease id: ([a-z0-9-]+)\s*$/m.exec(text)?.[1];
  const place = /^- Jurisdiction: ([A-Za-z]+)/m.exec(text)?.[1]?.toLowerCase();
  const signedOn = /^- Signed on: (\d{4}-\d{2}-\d{2})\s*$/m.exec(text)?.[1];
  const jurisdiction = place ? JURISDICTION_NAMES[place] : undefined;
  if (!title || !id || !jurisdiction || !signedOn) return null;
  return { id, place: title, title, jurisdiction: jurisdictionInfo(jurisdiction), signedOn };
}

/** Each lease's short description from the README's table ("| `fl-lease-01`, Miami apartment
 * | ..."), keyed by id. The titles repeat ("Lease of a Dwelling" three times), so this is how a
 * reader tells the leases apart. */
export function parseLeasePlaces(readme: string): Map<string, string> {
  const places = new Map<string, string>();
  for (const match of readme.matchAll(/^\| `([a-z0-9-]+)`, ([^|]+?) \|/gm)) {
    const [, id, place] = match;
    if (id && place) places.set(id, place.trim());
  }
  return places;
}

/** In the fixed jurisdiction order, then by id. */
export function sortLeases(leases: SampleLease[]): SampleLease[] {
  const rank = (lease: SampleLease) => JURISDICTION_IDS.indexOf(lease.jurisdiction.id);
  return [...leases].sort((a, b) => rank(a) - rank(b) || a.id.localeCompare(b.id));
}
