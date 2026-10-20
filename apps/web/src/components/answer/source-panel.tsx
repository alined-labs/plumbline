"use client";

import { Dialog } from "@base-ui/react/dialog";
import type { Citation } from "@plumbline/ts-client";
import { useRef, useState, type RefObject } from "react";

import { CheckIcon, CopyIcon, ExternalLinkIcon, XIcon } from "@/components/icons";
import { CodeBadge } from "@/components/ui/badge";
import { buttonClass } from "@/components/ui/button";
import { jurisdictionInfo } from "@/lib/jurisdictions";
import { sourceFor } from "@/lib/laws";
import { useCopy } from "@/lib/use-copy";

import { StatuteQuote } from "./statute-quote";

/** SourcePanel spec: the cited passage where it lives. A focus-trapped Base UI Dialog: opening
 * moves focus to the title, Escape closes it and focus returns to the marker or card that
 * opened it. From 768px it slides over the conversation from the right; below, it is a
 * bottom sheet. Over its scrim it is a dialog, so it takes the dialog layer. */
export function SourcePanel({
  citation,
  onClose,
  opener,
}: {
  /** The open source, or null when the panel is closed. */
  citation: Citation | null;
  onClose: () => void;
  opener: RefObject<HTMLElement | null>;
}) {
  const title = useRef<HTMLHeadingElement | null>(null);
  // Keep showing the last source while the panel slides out, rather than an empty panel.
  const [shown, setShown] = useState(citation);
  if (citation && citation !== shown) setShown(citation);
  return (
    <Dialog.Root open={citation !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-(--pl-z-overlay) bg-overlay transition-opacity duration-(--pl-duration-base) data-ending-style:opacity-0 data-starting-style:opacity-0" />
        <Dialog.Popup
          initialFocus={title}
          finalFocus={opener}
          className="fixed z-(--pl-z-dialog) flex flex-col border-border bg-surface shadow-3 transition-transform ease-enter max-md:inset-x-0 max-md:bottom-0 max-md:h-9/10 max-md:rounded-t-xl max-md:border-t max-md:duration-(--pl-duration-slow) max-md:data-ending-style:translate-y-full max-md:data-starting-style:translate-y-full md:inset-y-0 md:right-0 md:w-(--pl-panel-width) md:max-w-full md:border-l md:duration-(--pl-duration-base) md:data-ending-style:translate-x-full md:data-starting-style:translate-x-full"
        >
          {shown && <PanelContent citation={shown} title={title} />}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PanelContent({
  citation,
  title,
}: {
  citation: Citation;
  title: RefObject<HTMLHeadingElement | null>;
}) {
  const { n, label, ref, gloss } = citation;
  const source = sourceFor(ref.law, ref.edition);
  const [copied, copy] = useCopy();
  const reference = [`${label}, ${source?.title ?? ref.law} (edition ${ref.edition})`, source?.url]
    .filter(Boolean)
    .join("\n");

  return (
    <>
      <header className="flex items-start gap-3 border-b border-border px-6 pb-4 pt-5">
        <div className="flex flex-1 flex-col gap-1">
          <p className="flex items-center gap-2">
            <CodeBadge code={jurisdictionInfo(ref.jurisdiction).code} />
            <span className="font-mono text-eyebrow uppercase text-fg-muted">Source {n}</span>
          </p>
          <Dialog.Title ref={title} tabIndex={-1} className="text-heading-3">
            {label}
          </Dialog.Title>
          <p className="text-small text-fg-muted">
            {source ? `${source.title}, edition ${ref.edition}` : `Edition ${ref.edition}`}
          </p>
        </div>
        <Dialog.Close
          aria-label="Close source panel"
          className={buttonClass({ variant: "ghost", size: "sm", icon: true })}
        >
          <XIcon />
        </Dialog.Close>
      </header>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-6 py-5">
        <StatuteQuote citation={citation} />
        {gloss && (
          <p className="text-body text-fg-muted">
            <span className="font-medium text-fg">In English: </span>
            {gloss}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void copy(reference)}
            className={buttonClass({ size: "sm" })}
          >
            {copied ? <CheckIcon /> : <CopyIcon />}
            {copied ? "Reference copied" : "Copy reference"}
          </button>
          {source && (
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className={buttonClass({ variant: "ghost", size: "sm" })}
            >
              <ExternalLinkIcon />
              Open original
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          )}
        </div>
      </div>
    </>
  );
}
