import type { Metadata } from "next";

import { PagePending } from "@/components/states/page-pending";

export const metadata: Metadata = { title: "Check a lease · Plumbline" };

export default function CheckLeasePage() {
  return (
    <PagePending title="Check a lease">
      Upload a lease and see each clause beside the statute it was checked against. Lease checking
      opens when the checker is connected.
    </PagePending>
  );
}
