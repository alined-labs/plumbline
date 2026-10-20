import type { Citation } from "@plumbline/ts-client";

/** CitationMarker spec: the source number after the claim it supports. A button, so it is in
 * the tab order, named after its source. Only verified citations reach it. */
export function CitationMarker({
  citation,
  onSelect,
}: {
  citation: Citation;
  onSelect: (n: number) => void;
}) {
  return (
    <button
      type="button"
      aria-label={`Source ${citation.n}: ${citation.label}`}
      onClick={() => onSelect(citation.n)}
      className="mx-px inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-sm bg-accent-subtle px-1 align-middle font-mono text-code-sm font-semibold text-accent-text hover:bg-accent-subtle-hover"
    >
      {citation.n}
    </button>
  );
}
