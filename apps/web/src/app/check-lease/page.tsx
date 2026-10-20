import type { Metadata } from "next";

import { LeaseCheck } from "@/components/lease/lease-check";

export const metadata: Metadata = {
  title: "Check a lease · Plumbline",
  description:
    "Upload a lease and see each clause beside the statute it was checked against. Legal information, not legal advice.",
};

export default function CheckLeasePage() {
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-heading-1">Check a lease</h1>
        <p className="text-body text-fg-muted">
          Upload a lease and see each clause beside the statute it was checked against. Names, ID
          numbers and addresses are removed before any model reads it.
        </p>
      </header>
      <LeaseCheck />
    </div>
  );
}
