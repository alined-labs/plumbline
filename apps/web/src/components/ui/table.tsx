import type { ReactNode } from "react";

// Table spec: dense rows people compare, tabular numerals, numbers right-aligned, the column
// that names the row in semibold. A wide table scrolls inside its own box, which the keyboard
// can reach and scroll, so the page never scrolls sideways.

export function Table({
  label,
  caption,
  children,
}: {
  /** The scroll box's name, for a reader moving between regions. */
  label: string;
  /** What the table shows, read before its rows. */
  caption: ReactNode;
  children: ReactNode;
}) {
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      // Relative, so the screen-reader-only text in far columns stays clipped inside the box
      // rather than widening the page.
      className="relative overflow-x-auto rounded-lg border border-border"
    >
      <table className="w-full border-separate border-spacing-0 text-ui text-fg tabular-nums">
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}

export function Th({ children, num = false }: { children: ReactNode; num?: boolean }) {
  return (
    <th
      scope="col"
      className={`sticky top-0 whitespace-nowrap border-b border-border bg-bg-subtle px-3 py-2 text-micro font-medium text-fg-muted ${num ? "text-right" : "text-left"}`}
    >
      {children}
    </th>
  );
}

/** The cell that names its row: a row header, in semibold. */
export function RowHead({ children }: { children: ReactNode }) {
  return (
    <th
      scope="row"
      className="border-b border-border-subtle px-3 py-2.5 text-left align-top font-semibold group-last:border-b-0"
    >
      {children}
    </th>
  );
}

export function Td({ children, num = false }: { children: ReactNode; num?: boolean }) {
  return (
    <td
      className={`border-b border-border-subtle px-3 py-2.5 align-top group-last:border-b-0 ${num ? "text-right" : "text-left"}`}
    >
      {children}
    </td>
  );
}

export function Tr({ children }: { children: ReactNode }) {
  return <tr className="group hover:bg-bg-hover">{children}</tr>;
}
