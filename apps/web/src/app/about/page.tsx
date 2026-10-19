import type { Metadata } from "next";

import { PagePending } from "@/components/states/page-pending";

export const metadata: Metadata = { title: "About · Plumbline" };

export default function AboutPage() {
  return (
    <PagePending title="About Plumbline">
      Plumbline answers tenancy-law questions from the official statutes of Dubai, Spain, Colombia
      and Florida, and cites the article behind every claim. It gives legal information, not legal
      advice. Its limitations and how it is built are written up here soon.
    </PagePending>
  );
}
