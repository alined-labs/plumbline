import { dataParts, messageText, type PlumblineMessage } from "@/lib/messages";

/** One assistant answer: its text, its citations and what produced it. The seed renders
 * plain text; Phase 7 adds the citation chips, the source panel and sanitized Markdown. */
export function MessageView({ message }: { message: PlumblineMessage }) {
  const text = messageText(message);
  const citations = dataParts(message, "citation");
  const answer = dataParts(message, "answer").at(-1);
  const trace = dataParts(message, "trace").at(-1);

  return (
    <article className="rounded-lg border border-border bg-surface p-4">
      <p className="whitespace-pre-wrap">{text}</p>
      {answer?.status === "abstained" && (
        <p className="mt-3 text-small text-warning">
          Plumbline declined to answer{answer.abstain_reason ? `: ${answer.abstain_reason}` : "."}
        </p>
      )}
      {answer?.status === "partial" && (
        <p className="mt-3 text-small text-warning">
          Partial answer: part of the question is outside the indexed law.
        </p>
      )}
      {citations.length > 0 && (
        <ol aria-label="Citations" className="mt-4 space-y-2 text-small">
          {citations.map((citation) => (
            <li key={citation.n}>
              <span className="font-mono">[{citation.n}]</span> {citation.label}
              {!citation.verified && (
                <span className="text-danger"> (not found in the source)</span>
              )}
              <blockquote
                lang={citation.language}
                className="mt-1 border-l-2 border-border pl-3 text-fg-muted"
              >
                {citation.quote}
              </blockquote>
              {citation.gloss && <p className="mt-1 pl-3 text-fg-muted">{citation.gloss}</p>}
            </li>
          ))}
        </ol>
      )}
      {trace && (
        <p className="mt-4 text-micro text-fg-muted">
          {trace.model} · {trace.tier} tier{trace.cached ? " · replayed" : ""}
        </p>
      )}
    </article>
  );
}
