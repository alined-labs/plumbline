import type { Citation } from "@plumbline/ts-client";

import { CodeBadge } from "@/components/ui/badge";
import { jurisdictionInfo } from "@/lib/jurisdictions";

/** SourceCard spec: one cited passage under the answer, numbered like its markers; choosing it
 * opens the passage in the source panel, and it keeps a 2px accent edge while that is open.
 * The quote is the law's own words, in its own language, so it is set in the serif with its
 * lang. */
export function SourceCard({
  citation,
  selected,
  onOpen,
}: {
  citation: Citation;
  selected: boolean;
  onOpen: (n: number, opener: HTMLElement) => void;
}) {
  const { n, label, ref, page, quote, gloss, language } = citation;
  return (
    <li>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={selected}
        onClick={(event) => onOpen(n, event.currentTarget)}
        className="grid h-full w-full grid-cols-[--spacing(5.5)_minmax(0,1fr)] gap-x-2.5 gap-y-1 rounded-lg border border-border bg-surface px-3.5 py-3 text-left hover:border-border-strong hover:bg-bg-subtle aria-expanded:border-accent aria-expanded:ring-1 aria-expanded:ring-inset aria-expanded:ring-accent"
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
        <span lang={language} className="line-clamp-3 font-serif text-quote-sm text-fg">
          {quote}
        </span>
        {gloss && <span className="text-small text-fg-muted">{gloss}</span>}
      </button>
    </li>
  );
}
