import type { Citation } from "@plumbline/ts-client";
import { useEffect, useRef } from "react";

import { CircleCheckIcon } from "@/components/icons";
import { CodeBadge } from "@/components/ui/badge";
import { spanRange, splitAtSpan, type ChunkArticle } from "@/lib/article";
import { jurisdictionInfo } from "@/lib/jurisdictions";
import { isWithheld } from "@/lib/replay";

/** StatuteQuote spec: the law's own words, verbatim, in the serif on a sunken ground, headed by
 * its citation and its verification. Serif means the statute speaks, so nothing else goes
 * here: Plumbline's gloss stays outside it, in the sans.
 *
 * With the article (the API's text as published) the passage is the article itself with the
 * cited words marked and the range they occupy; without it, or when the quote is not found in
 * it, the passage is the quote the answer carried. A restricted source (its publisher's terms
 * forbid republishing it) is only ever the quote, with no range: the API sends no more, and a
 * range would point into text the reader cannot see. */
export function StatuteQuote({
  citation,
  article,
}: {
  citation: Citation;
  article?: ChunkArticle | undefined;
}) {
  const { label, ref, quote, language, verified } = citation;
  const cut =
    article && !article.restricted ? splitAtSpan(article.article.text, article.span) : null;
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
      {article && cut && article.span ? (
        <>
          <ArticlePassage language={article.article.language} cut={cut} />
          <p className="font-mono text-code-sm text-fg-subtle">
            {spanRange(article.article.text, article.span)}
          </p>
        </>
      ) : isWithheld(quote) ? (
        <p className="text-body text-fg-muted">
          The publisher&apos;s terms do not let us republish this passage. Open the original to read
          it.
        </p>
      ) : (
        <blockquote lang={language} className="font-serif text-quote text-fg">
          {quote}
        </blockquote>
      )}
    </figure>
  );
}

/** The article in a box that scrolls on its own, a keyboard-reachable region, with the cited
 * words a third of the way down so the reader meets them with their context above. */
function ArticlePassage({
  language,
  cut,
}: {
  language: string;
  cut: NonNullable<ReturnType<typeof splitAtSpan>>;
}) {
  const region = useRef<HTMLDivElement>(null);
  const cited = useRef<HTMLElement>(null);
  useEffect(() => {
    const box = region.current;
    const mark = cited.current;
    if (box && mark) box.scrollTop = Math.max(0, mark.offsetTop - box.clientHeight / 3);
  }, [cut]);
  return (
    <div
      ref={region}
      role="region"
      aria-label="Article text"
      tabIndex={0}
      className="relative max-h-72 overflow-y-auto rounded-xs"
    >
      <blockquote lang={language} className="font-serif text-quote whitespace-pre-line text-fg">
        {cut.before}
        <mark
          ref={cited}
          className="rounded-xs bg-highlight-strong px-0.5 text-inherit shadow-[inset_0_-2px_0_var(--pl-color-highlight-edge)] box-decoration-clone"
        >
          {cut.cited}
        </mark>
        {cut.after}
      </blockquote>
    </div>
  );
}
