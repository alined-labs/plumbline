import type { Citation } from "@plumbline/ts-client";

import { CodeBadge } from "@/components/ui/badge";
import { jurisdictionInfo } from "@/lib/jurisdictions";

/** SourceCard spec: one cited passage under the answer, numbered like its markers. The quote
 * is the law's own words, in its own language, so it is set in the serif with its lang. */
export function SourceCard({
  citation,
  id,
  selected,
}: {
  citation: Citation;
  id: string;
  selected: boolean;
}) {
  const { n, label, ref, page, quote, gloss, language } = citation;
  return (
    <li
      id={id}
      tabIndex={-1}
      data-selected={selected || undefined}
      className="grid grid-cols-[--spacing(5.5)_minmax(0,1fr)] gap-x-2.5 gap-y-1 rounded-lg border border-border bg-surface px-3.5 py-3 data-selected:border-accent data-selected:ring-1 data-selected:ring-inset data-selected:ring-accent"
    >
      <span
        aria-hidden="true"
        className="row-span-4 flex h-5 items-center justify-center self-start rounded-sm bg-accent-subtle font-mono text-code-sm font-semibold text-accent-text"
      >
        {n}
      </span>
      <span className="text-ui-strong">
        <span className="sr-only">Source {n}: </span>
        {label}
      </span>
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-small text-fg-muted">
        <CodeBadge code={jurisdictionInfo(ref.jurisdiction).code} /> Edition {ref.edition}
        {page !== null && page !== undefined && ` · p. ${page}`}
      </span>
      <blockquote lang={language} className="line-clamp-3 font-serif text-quote-sm">
        {quote}
      </blockquote>
      {gloss && <p className="text-small text-fg-muted">{gloss}</p>}
    </li>
  );
}
