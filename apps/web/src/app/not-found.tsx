import type { Metadata } from "next";
import Link from "next/link";

import { buttonClass } from "@/components/ui/button";

export const metadata: Metadata = { title: "Page not found · Plumbline" };

/** EmptyState spec, for a list of nothing: what was looked for, in the reader's terms, and
 * one action. */
export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-160 flex-col items-center gap-4 py-12 text-center">
      <h1 className="text-heading-1">{"There's no page at this address"}</h1>
      <p className="text-body text-fg-muted">
        The link may be mistyped or out of date. Ask a question, or pick a page from the menu.
      </p>
      <Link href="/" className={buttonClass({ variant: "primary", size: "lg" })}>
        Ask a question
      </Link>
    </div>
  );
}
