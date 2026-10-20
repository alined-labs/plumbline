import type { Citation } from "@plumbline/ts-client";
import Markdown from "react-markdown";

import { sourceNumber } from "@/lib/answer";

import { CitationMarker } from "./citation-marker";

// Model output is untrusted (AGENTS.md 20): raw HTML is skipped, only prose elements render,
// and the only links are the #source-n markers, which become citation buttons. Any other
// link keeps its words and loses its address.
const ALLOWED = ["p", "strong", "em", "ul", "ol", "li", "code", "br", "a"];

/** Plumbline's own words in body-lg sans; the law is quoted only in source cards. */
export function AnswerBody({
  markdown,
  citations,
  onSelect,
}: {
  markdown: string;
  citations: Citation[];
  onSelect: (n: number) => void;
}) {
  const byNumber = new Map(citations.map((citation) => [citation.n, citation]));
  return (
    <div className="text-body-lg [&_code]:font-mono [&_li]:mb-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_p:not(:last-child)]:mb-3 [&_ul]:list-disc [&_ul]:pl-5">
      <Markdown
        allowedElements={ALLOWED}
        unwrapDisallowed
        skipHtml
        urlTransform={(url) => (sourceNumber(url) === null ? "" : url)}
        components={{
          a({ href, children }) {
            const n = sourceNumber(href);
            const citation = n === null ? undefined : byNumber.get(n);
            return citation ? (
              <CitationMarker citation={citation} onSelect={onSelect} />
            ) : (
              <>{children}</>
            );
          },
        }}
      >
        {markdown}
      </Markdown>
    </div>
  );
}
