import type { Citation } from "@plumbline/ts-client";

/** CitationMarker spec: the source number after the claim it supports. A button, so it is in
 * the tab order, named after its source; it opens the source panel and stays active (accent
 * fill, aria-expanded) while its passage is open. Only verified citations reach it. */
export function CitationMarker({
  citation,
  active,
  onOpen,
}: {
  citation: Citation;
  active: boolean;
  onOpen: (n: number, opener: HTMLElement) => void;
}) {
  return (
    <button
      type="button"
      aria-label={`Source ${citation.n}: ${citation.label}`}
      aria-haspopup="dialog"
      aria-expanded={active}
      onClick={(event) => onOpen(citation.n, event.currentTarget)}
      className="mx-px inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-sm bg-accent-subtle px-1 align-middle font-mono text-code-sm font-semibold text-accent-text hover:bg-accent-subtle-hover aria-expanded:bg-accent aria-expanded:text-accent-fg"
    >
      {citation.n}
    </button>
  );
}
