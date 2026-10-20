import type { Metadata } from "next";

import { EvalsView } from "@/components/evals/evals-view";
import { PagePending } from "@/components/states/page-pending";
import { loadEvals } from "@/lib/evals-files";

export const metadata: Metadata = {
  title: "Evaluation · Plumbline",
  description:
    "How often Plumbline finds and cites the right article, answers correctly and declines when it should, with 95% intervals.",
};

/** Built from the committed results files: the static export reads them once, at build. */
export default function EvalsPage() {
  const data = loadEvals();
  if (data.runs.length === 0 && !data.agreement) {
    return (
      <PagePending title="Evaluation">
        How often Plumbline cites the right article, answers correctly and declines when it should,
        measured on a public benchmark. The results appear here after the first published run.
      </PagePending>
    );
  }
  return <EvalsView data={data} />;
}
