import type { Citation } from "@plumbline/ts-client";
import { createContext, memo, useContext, type ComponentProps } from "react";
import Markdown, { type Components, type ExtraProps } from "react-markdown";

import { sourceNumber } from "@/lib/answer";

import { CitationMarker } from "./citation-marker";

// Model output is untrusted (AGENTS.md 20): raw HTML is skipped, only prose elements render,
// and the only links are the #source-n markers, which become citation buttons. Any other
// link keeps its words and loses its address.
const ALLOWED = ["p", "strong", "em", "ul", "ol", "li", "code", "br", "a"];

type Markers = {
  byNumber: Map<number, Citation>;
  /** The source open in the panel, whose markers show as active. */
  active: number | null;
  onOpen: (n: number, opener: HTMLElement) => void;
};

// The markers read their citations from context so that the `a` component below is one
// stable type: react-markdown's components rebuilt on each render would remount every marker,
// losing the button the panel returns focus to.
const MarkersContext = createContext<Markers | null>(null);

function MarkerLink({ href, children }: ComponentProps<"a"> & ExtraProps) {
  const markers = useContext(MarkersContext);
  const n = sourceNumber(href);
  const citation = n === null ? undefined : markers?.byNumber.get(n);
  return citation && markers ? (
    <CitationMarker citation={citation} active={markers.active === n} onOpen={markers.onOpen} />
  ) : (
    <>{children}</>
  );
}

const COMPONENTS: Components = { a: MarkerLink };

const urlTransform = (url: string) => (sourceNumber(url) === null ? "" : url);

/** One paragraph or list. While an answer streams only its last block grows, so the blocks
 * before it are parsed once instead of on every update (docs/notes/streamed-answer-profile.md).
 * The markers inside follow the context, so only the text and the citations matter here. */
const MarkdownBlock = memo(
  function MarkdownBlock({ markdown }: { markdown: string; citationsKey: string }) {
    return (
      <Markdown
        allowedElements={ALLOWED}
        unwrapDisallowed
        skipHtml
        urlTransform={urlTransform}
        components={COMPONENTS}
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
  active,
  onOpen,
}: {
  markdown: string;
  citations: Citation[];
  active: number | null;
  onOpen: (n: number, opener: HTMLElement) => void;
}) {
  const byNumber = new Map(citations.map((citation) => [citation.n, citation]));
  const citationsKey = citations.map((citation) => `${citation.n}:${citation.chunk_id}`).join();
  // Blank lines separate Markdown blocks, so splitting there renders the same elements.
  const blocks = markdown.split(/\n{2,}/);
  return (
    <MarkersContext value={{ byNumber, active, onOpen }}>
      <div className="text-body-lg [&_code]:font-mono [&_li]:mb-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_p:not(:last-child)]:mb-3 [&_ul]:list-disc [&_ul]:pl-5">
        {blocks.map((block, i) => (
          <MarkdownBlock key={i} markdown={block} citationsKey={citationsKey} />
        ))}
      </div>
    </MarkersContext>
  );
}
