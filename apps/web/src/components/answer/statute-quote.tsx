import type { Citation } from "@plumbline/ts-client";

import { CircleCheckIcon } from "@/components/icons";
import { CodeBadge } from "@/components/ui/badge";
import { jurisdictionInfo } from "@/lib/jurisdictions";

/** StatuteQuote spec: the law's own words, verbatim, in the serif on a sunken ground, headed by
 * its citation and its verification. Serif means the statute speaks, so nothing else goes
 * here: Plumbline's gloss stays outside it, in the sans. */
export function StatuteQuote({ citation }: { citation: Citation }) {
  const { label, ref, quote, language, verified } = citation;
  return (
    <figure className="flex flex-col gap-2 rounded-lg bg-surface-sunken px-4 py-3">
      <figcaption className="flex flex-wrap items-center gap-x-2 gap-y-1 text-small text-fg-muted">
        <CodeBadge code={jurisdictionInfo(ref.jurisdiction).code} />{" "}
        <strong className="font-semibold text-fg">{label}</strong> Edition {ref.edition}
        {verified && (
          <>
            {" "}
            <span className="inline-flex items-center gap-1 font-medium text-success">
              <CircleCheckIcon size={14} strokeWidth={2} />
              Verified
            </span>
          </>
        )}
      </figcaption>
      <blockquote lang={language} className="font-serif text-quote text-fg">
        {quote}
      </blockquote>
    </figure>
  );
}
