"use client";

import { Dialog } from "@base-ui/react/dialog";
import type { Citation } from "@plumbline/ts-client";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type RefObject,
} from "react";

import { CheckIcon, CopyIcon, ExternalLinkIcon, XIcon } from "@/components/icons";
import { CodeBadge } from "@/components/ui/badge";
import { buttonClass } from "@/components/ui/button";
import { jurisdictionInfo } from "@/lib/jurisdictions";
import { sourceFor } from "@/lib/laws";
import { useCopy } from "@/lib/use-copy";
import { useMediaQuery } from "@/lib/use-media-query";

import { StatuteQuote } from "./statute-quote";

/** What the panel is showing: one source of one answer. */
export type PanelSubject = {
  /** The answer's message id: markers in different answers can share a number. */
  messageId: string;
  /** The open source's number. */
  n: number;
  /** The answer's verified sources, in first-citation order. */
  citations: Citation[];
};

/** SourcePanel spec: the cited passage where it lives, a Base UI Dialog.
 *
 * - From 1024px it is the AppShell's third pane, rendered into `slot` beside the conversation:
 *   focus stays inside it ("trap-focus") but the page stays readable and clickable, so another
 *   marker switches the source, and the reader can drag or key its edge between the token
 *   widths.
 * - From 768px it overlays the conversation from the right, with no scrim (the z-panel layer).
 * - Below 768px it is a bottom sheet at 90% height with a grab handle and a scrim.
 *
 * Opening moves focus to the title; Escape closes it and focus returns to the marker or card
 * that opened it. */
export function SourcePanel({
  subject,
  onClose,
  opener,
  slot,
}: {
  /** The open source, or null when the panel is closed. */
  subject: PanelSubject | null;
  onClose: () => void;
  opener: RefObject<HTMLElement | null>;
  /** The shell's third pane, once it has mounted. */
  slot: HTMLElement | null;
}) {
  const wide = useMediaQuery("(min-width: 1024px)");
  const title = useRef<HTMLHeadingElement | null>(null);
  const [width, setWidth] = useState<number | null>(null);
  // Keep showing the last source while the panel slides out, rather than an empty panel.
  const [shown, setShown] = useState(subject);
  if (subject && subject !== shown) setShown(subject);

  // A marker clicked while the panel is already open switches the source: the dialog does not
  // reopen, so focus moves to the new title here.
  const current = subject ? `${subject.messageId}:${subject.n}` : null;
  useEffect(() => {
    if (current) title.current?.focus();
  }, [current]);

  const citation = shown?.citations.find((candidate) => candidate.n === shown.n);

  return (
    <Dialog.Root
      open={subject !== null}
      onOpenChange={(open) => !open && onClose()}
      modal={wide ? "trap-focus" : true}
      disablePointerDismissal={wide}
    >
      <Dialog.Portal container={wide ? slot : undefined}>
        <Dialog.Backdrop className="fixed inset-0 z-(--pl-z-overlay) bg-overlay transition-opacity duration-(--pl-duration-base) data-ending-style:opacity-0 data-starting-style:opacity-0 md:hidden" />
        <Dialog.Popup
          initialFocus={title}
          finalFocus={opener}
          style={wide && width ? { width } : undefined}
          className="fixed flex flex-col border-border bg-surface shadow-3 transition-transform ease-enter max-md:inset-x-0 max-md:bottom-0 max-md:z-(--pl-z-dialog) max-md:h-9/10 max-md:rounded-t-xl max-md:border-t max-md:duration-(--pl-duration-slow) max-md:data-ending-style:translate-y-full max-md:data-starting-style:translate-y-full md:inset-y-0 md:right-0 md:z-(--pl-z-panel) md:w-(--pl-panel-width) md:max-w-full md:border-l md:duration-(--pl-duration-base) md:data-ending-style:translate-x-full md:data-starting-style:translate-x-full lg:relative lg:h-dvh lg:max-w-(--pl-panel-max-width) lg:min-w-(--pl-panel-min-width) lg:shadow-none lg:transition-none"
        >
          <span
            aria-hidden="true"
            className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-border-strong md:hidden"
          />
          {wide && <ResizeHandle width={width} onWidth={setWidth} />}
          {citation && <PanelContent citation={citation} title={title} />}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

const KEY_STEP = 16;

function readPx(property: string): number {
  return Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue(property));
}

/** The panel's left edge as a window splitter: drag it, or focus it and use the arrow keys
 * (Home and End jump to the ends). The range is the panel-min-width and panel-max-width
 * tokens, so the numbers live with the design system. */
function ResizeHandle({
  width,
  onWidth,
}: {
  width: number | null;
  onWidth: (width: number) => void;
}) {
  // Read once, when the handle first renders in the browser: the range and the default width
  // are tokens, and the handle only exists once the panel has opened beside the conversation.
  const [limits] = useState(() => ({
    min: readPx("--pl-panel-min-width"),
    max: readPx("--pl-panel-max-width"),
    initial: readPx("--pl-panel-width"),
  }));
  const drag = useRef<{ x: number; width: number } | null>(null);
  const value = width ?? limits.initial;
  const clamp = (next: number) => Math.min(limits.max, Math.max(limits.min, next));

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, width: value };
  }
  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    // The panel is on the right, so dragging its edge left makes it wider.
    if (drag.current) onWidth(clamp(drag.current.width + drag.current.x - event.clientX));
  }
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const next = {
      ArrowLeft: value + KEY_STEP,
      ArrowRight: value - KEY_STEP,
      Home: limits.min,
      End: limits.max,
    }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    onWidth(clamp(next));
  }

  return (
    // A focusable separator is a widget (the window splitter pattern), so it takes the keys.
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize source panel"
      aria-valuemin={limits.min}
      aria-valuemax={limits.max}
      aria-valuenow={Math.round(value)}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={() => (drag.current = null)}
      onPointerCancel={() => (drag.current = null)}
      onKeyDown={onKeyDown}
      className="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize touch-none after:absolute after:inset-y-0 after:left-0.75 after:w-0.5 after:bg-transparent hover:after:bg-accent focus-visible:after:bg-accent"
    />
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
