import type { Metadata } from "next";

import { PagePending } from "@/components/states/page-pending";

export const metadata: Metadata = { title: "Evaluation · Plumbline" };

export default function EvalsPage() {
  return (
    <PagePending title="Evaluation">
      How often Plumbline cites the right article, answers correctly and declines when it should,
      measured on a public benchmark. The results appear here after the first published run.
    </PagePending>
  );
}
