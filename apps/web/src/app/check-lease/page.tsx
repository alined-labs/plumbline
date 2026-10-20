import type { Metadata } from "next";

import { LeaseCheck } from "@/components/lease/lease-check";
import { LEASE_UPLOADS } from "@/lib/sample-leases";
import { loadSampleLeases } from "@/lib/sample-leases-files";

export const metadata: Metadata = {
  title: "Check a lease · Plumbline",
  description:
    "Upload a lease and see each clause beside the statute it was checked against. Legal information, not legal advice.",
};

export default function CheckLeasePage() {
  const samples = LEASE_UPLOADS ? undefined : loadSampleLeases();
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-heading-1">Check a lease</h1>
        <p className="text-body text-fg-muted">
          {samples
            ? "Check a lease and see each clause beside the statute it was checked against."
            : "Upload a lease and see each clause beside the statute it was checked against. Names, ID numbers and addresses are removed before any model reads it."}
        </p>
      </header>
      <LeaseCheck samples={samples} />
    </div>
  );
}
