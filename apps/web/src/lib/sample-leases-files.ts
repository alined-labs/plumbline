import fs from "node:fs";
import path from "node:path";

import { parseLeaseHeader, parseLeasePlaces, sortLeases, type SampleLease } from "./sample-leases";

// Read at build time only: the lease page's picker and the static lease files.
const LEASES_DIR = path.join(process.cwd(), "..", "..", "data", "leases");

/** "fl-lease-01.md" and the like; the README and the findings file are not leases. */
function leaseFiles(dir: string): string[] {
  return fs.readdirSync(dir).filter((name) => /^[a-z]+-lease-\d+\.md$/.test(name));
}

export function readLeaseText(id: string, dir: string = LEASES_DIR): string {
  return fs.readFileSync(path.join(dir, `${id}.md`), "utf8");
}

export function loadSampleLeases(dir: string = LEASES_DIR): SampleLease[] {
  const readme = path.join(dir, "README.md");
  const places = parseLeasePlaces(fs.existsSync(readme) ? fs.readFileSync(readme, "utf8") : "");
  return sortLeases(
    leaseFiles(dir).flatMap((name) => {
      const lease = parseLeaseHeader(fs.readFileSync(path.join(dir, name), "utf8"));
      if (!lease || `${lease.id}.md` !== name) return [];
      return [{ ...lease, place: places.get(lease.id) ?? lease.title }];
    }),
  );
}
