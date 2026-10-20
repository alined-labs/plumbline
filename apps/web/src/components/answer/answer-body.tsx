import type { Citation } from "@plumbline/ts-client";
import { memo } from "react";
import Markdown from "react-markdown";

import { sourceNumber } from "@/lib/answer";

import { CitationMarker } from "./citation-marker";

// Model output is untrusted (AGENTS.md 20): raw HTML is skipped, only prose elements render,
// and the only links are the #source-n markers, which become citation buttons. Any other
// link keeps its words and loses its address.
const ALLOWED = ["p", "strong", "em", "ul", "ol", "li", "code", "br", "a"];

type BlockProps = {
  markdown: string;
  /** Changes only when the citations do; the map and the callback are rebuilt on every
   * streamed update with the same contents, so the comparison below ignores them. */
  citationsKey: string;
  byNumber: Map<number, Citation>;
  onSelect: (n: number) => void;
};

/** One paragraph or list. While an answer streams only its last block grows, so the blocks
 * before it are parsed once instead of on every update (docs/notes/streamed-answer-profile.md). */
const MarkdownBlock = memo(
  function MarkdownBlock({ markdown, byNumber, onSelect }: BlockProps) {
    return (
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
    );
  },
  (before, after) =>
    before.markdown === after.markdown && before.citationsKey === after.citationsKey,
);

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
  const citationsKey = citations.map((citation) => `${citation.n}:${citation.chunk_id}`).join();
  // Blank lines separate Markdown blocks, so splitting there renders the same elements.
  const blocks = markdown.split(/\n{2,}/);
  return (
    <div className="text-body-lg [&_code]:font-mono [&_li]:mb-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_p:not(:last-child)]:mb-3 [&_ul]:list-disc [&_ul]:pl-5">
      {blocks.map((block, i) => (
        <MarkdownBlock
          key={i}
          markdown={block}
          citationsKey={citationsKey}
          byNumber={byNumber}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
