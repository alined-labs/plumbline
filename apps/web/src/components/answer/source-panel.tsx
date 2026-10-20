"use client";

import { Dialog } from "@base-ui/react/dialog";
import { Tabs } from "@base-ui/react/tabs";
import type { Citation, TraceSummary } from "@plumbline/ts-client";
import { useQuery } from "@tanstack/react-query";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  type RefObject,
} from "react";

import { CheckIcon, CopyIcon, ExternalLinkIcon, XIcon } from "@/components/icons";
import { CodeBadge } from "@/components/ui/badge";
import { buttonClass } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { articleQuery, type PublishedArticle } from "@/lib/article";
import { formatDate } from "@/lib/dates";
import { jurisdictionInfo } from "@/lib/jurisdictions";
import { sourceFor } from "@/lib/laws";
import type { Run } from "@/lib/run";
import { dollars, duration, middleTruncate, spansFromTrace } from "@/lib/trace";
import { useCopy } from "@/lib/use-copy";
import { useMediaQuery } from "@/lib/use-media-query";

import { TraceWaterfall } from "../trace/trace-waterfall";

import { StatusSteps } from "./status-steps";
import { StatuteQuote } from "./statute-quote";

export type PanelTab = "sources" | "trace";

/** What the panel is showing: one answer, on one of its two tabs. */
export type PanelSubject = {
  /** The answer's message id: markers in different answers can share a number. */
  messageId: string;
  /** The answer's verified sources, in first-citation order. */
  citations: Citation[];
  /** The open source's number; null when the panel was opened on the trace alone. */
  n: number | null;
  tab: PanelTab;
  trace: TraceSummary | undefined;
  /** The request's stages as the browser saw them, timed (the stream does not store them). */
  run: Run | undefined;
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
  onChange,
  onClose,
  opener,
  slot,
}: {
  /** The open answer, or null when the panel is closed. */
  subject: PanelSubject | null;
  /** Switches the source or the tab without reopening. */
  onChange: (patch: Partial<Pick<PanelSubject, "n" | "tab">>) => void;
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
  const current = subject ? `${subject.messageId}:${subject.n ?? "trace"}` : null;
  useEffect(() => {
    if (current) title.current?.focus();
  }, [current]);

  const citation = shown?.citations.find((candidate) => candidate.n === shown.n);
  const open = subject ?? shown;

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
          {shown && open && (
            <>
              <PanelHeader citation={citation} title={title} />
              <Tabs.Root
                value={open.tab}
                onValueChange={(tab: PanelTab) =>
                  onChange(
                    tab === "sources"
                      ? { tab, n: open.n ?? open.citations[0]?.n ?? null }
                      : { tab },
                  )
                }
                className="flex min-h-0 flex-1 flex-col"
              >
                <Tabs.List className="flex gap-5 border-b border-border px-6">
                  <Tabs.Tab value="sources" className={TAB}>
                    Sources
                    <span className="rounded-full bg-bg-active px-1.5 text-micro font-semibold tabular-nums text-fg-muted">
                      {open.citations.length}
                    </span>
                  </Tabs.Tab>
                  <Tabs.Tab value="trace" className={TAB}>
                    Trace
                  </Tabs.Tab>
                </Tabs.List>
                <Tabs.Panel value="sources" className="flex-1 overflow-y-auto px-6 py-5">
                  <SourcesPane citation={citation} subject={open} onChange={onChange} />
                </Tabs.Panel>
                <Tabs.Panel value="trace" className="flex-1 overflow-y-auto px-6 py-5">
                  <TracePane trace={open.trace} run={open.run} />
                </Tabs.Panel>
              </Tabs.Root>
            </>
          )}
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

// Tabs spec: ui medium labels in fg-muted, the current one in fg with a 2px accent underline
// that sits on the border rule.
const TAB =
  "-mb-px flex h-10 items-center gap-1.5 border-b-2 border-transparent text-ui font-medium text-fg-muted hover:text-fg data-active:border-accent data-active:text-fg";

/** The cited article, fetched when a source is open. The quote goes along so the API can say
 * where in the article it sits. */
function useArticle(citation: Citation | undefined) {
  return useQuery({
    ...articleQuery(citation?.chunk_id ?? "", citation?.quote ?? ""),
    enabled: Boolean(citation),
  });
}

/** What the edition says about the article's validity and dates: a provision that is repealed
 * or struck down is said so before its text, with the publisher's own note. */
function ArticleStatus({ article }: { article: PublishedArticle }) {
  const { status, validity_note, effective_from, effective_to, language } = article;
  const dates = [
    effective_from && `In force from ${formatDate(effective_from)}`,
    effective_to && `until ${formatDate(effective_to)}`,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <>
      {status !== "in_force" && (
        <Callout
          tone="warning"
          title={
            status === "repealed"
              ? "This provision is repealed."
              : "This provision was struck down."
          }
        >
          {validity_note ? (
            <span lang={language}>{validity_note}</span>
          ) : (
            "The edition's own note says it no longer applies."
          )}
        </Callout>
      )}
      {dates && <p className="text-small text-fg-muted">{dates}.</p>}
    </>
  );
}

function PanelHeader({
  citation,
  title,
}: {
  citation: Citation | undefined;
  title: RefObject<HTMLHeadingElement | null>;
}) {
  const source = citation && sourceFor(citation.ref.law, citation.ref.edition);
  const heading = useArticle(citation).data?.article.heading;
  return (
    <header className="flex items-start gap-3 px-6 pb-4 pt-5">
      <div className="flex flex-1 flex-col gap-1">
        {citation ? (
          <p className="flex items-center gap-2">
            <CodeBadge code={jurisdictionInfo(citation.ref.jurisdiction).code} />
            <span className="font-mono text-eyebrow uppercase text-fg-muted">
              Source {citation.n}
            </span>
          </p>
        ) : (
          <p className="font-mono text-eyebrow uppercase text-fg-muted">Trace</p>
        )}
        <Dialog.Title ref={title} tabIndex={-1} className="text-heading-3">
          {citation ? citation.label : "How this answer was produced"}
        </Dialog.Title>
        {citation && (
          <p className="text-small text-fg-muted">
            {heading && `${heading} · `}
            {source
              ? `${source.title}, edition ${citation.ref.edition}`
              : `Edition ${citation.ref.edition}`}
          </p>
        )}
      </div>
      <Dialog.Close
        aria-label="Close source panel"
        className={buttonClass({ variant: "ghost", size: "sm", icon: true })}
      >
        <XIcon />
      </Dialog.Close>
    </header>
  );
}

function SourcesPane({
  citation,
  subject,
  onChange,
}: {
  citation: Citation | undefined;
  subject: PanelSubject;
  onChange: (patch: { n: number }) => void;
}) {
  const [copied, copy] = useCopy();
  const article = useArticle(citation);
  if (!citation) {
    return <p className="text-body text-fg-muted">This answer cites no sources.</p>;
  }
  const { label, ref, gloss } = citation;
  const source = sourceFor(ref.law, ref.edition);
  const reference = [`${label}, ${source?.title ?? ref.law} (edition ${ref.edition})`, source?.url]
    .filter(Boolean)
    .join("\n");
  const others = subject.citations.filter((candidate) => candidate.n !== citation.n);

  return (
    <div className="flex flex-col gap-4">
      {article.data && <ArticleStatus article={article.data.article} />}
      <StatuteQuote citation={citation} article={article.data} />
      {article.isPending && (
        <p role="status" className="text-small text-fg-muted">
          Loading the whole article…
        </p>
      )}
      {article.isError && (
        <p className="text-small text-fg-muted">
          The article&apos;s full text isn&apos;t available right now, so this is the quoted passage
          alone.
        </p>
      )}
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
      {others.length > 0 && (
        <section aria-label="Other sources in this answer" className="flex flex-col gap-1.5">
          <h3 className="font-mono text-eyebrow uppercase text-fg-muted">Other sources</h3>
          <ul className="flex flex-col">
            {others.map((other) => (
              <li key={other.n}>
                <button
                  type="button"
                  onClick={() => onChange({ n: other.n })}
                  className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-ui hover:bg-bg-hover max-md:min-h-11"
                >
                  <span className="flex h-5 min-w-5 items-center justify-center rounded-sm bg-accent-subtle font-mono text-code-sm font-semibold text-accent-text">
                    {other.n}
                  </span>
                  <span className="sr-only">Source {other.n}: </span>
                  {other.label}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** The Trace tab: the stages as the browser saw them, then the server's own timings as a
 * waterfall, then what produced the answer. */
function TracePane({ trace, run }: { trace: TraceSummary | undefined; run: Run | undefined }) {
  if (!trace && !run) {
    return <p className="text-body text-fg-muted">There is no trace for this answer.</p>;
  }
  const { spans, total } = trace ? spansFromTrace(trace) : { spans: [], total: 0 };
  return (
    <div className="flex flex-col gap-6">
      {run && run.steps.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-ui-strong">As it happened</h3>
          <StatusSteps run={run} />
        </section>
      )}
      {spans.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-ui-strong">Where the time went</h3>
          <TraceWaterfall spans={spans} total={total} label="Time per stage" />
        </section>
      )}
      {trace && <TraceDetails trace={trace} />}
    </div>
  );
}

function TraceDetails({ trace }: { trace: TraceSummary }) {
  const rows: { name: string; value: ReactNode }[] = [
    { name: "Model", value: <span className="font-mono text-code-sm">{trace.model}</span> },
    { name: "Tier", value: `${trace.tier} tier` },
    { name: "Route", value: <span className="font-mono text-code-sm">{trace.route}</span> },
    { name: "Answer", value: trace.cached ? "Replayed from a recording" : "Generated live" },
    {
      name: "Tokens",
      value: `${trace.input_tokens.toLocaleString("en-GB")} in, ${trace.output_tokens.toLocaleString("en-GB")} out`,
    },
    { name: "Cost", value: dollars(trace.cost_usd) },
    { name: "Time", value: duration(Object.values(trace.timings_ms).reduce((a, b) => a + b, 0)) },
    { name: "Configuration", value: <Id value={trace.config_hash} note={trace.config_name} /> },
    { name: "Request", value: <Id value={trace.request_id} /> },
  ];
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-ui-strong">What produced it</h3>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 text-ui">
        {rows.map(({ name, value }) => (
          <div key={name} className="contents">
            <dt className="text-fg-muted">{name}</dt>
            <dd className="min-w-0 text-fg">{value}</dd>
          </div>
        ))}
      </dl>
      {trace.trace_url && (
        <a
          href={trace.trace_url}
          target="_blank"
          rel="noreferrer"
          className={buttonClass({ variant: "ghost", size: "sm", className: "self-start" })}
        >
          <ExternalLinkIcon />
          Open the full trace
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      )}
    </section>
  );
}

/** An ID or hash in the code face, truncated in the middle with the whole value kept for a
 * screen reader and for a hover (Table spec). */
function Id({ value, note }: { value: string; note?: string }) {
  return (
    <span className="font-mono text-code-sm" title={value}>
      <span aria-hidden="true">{middleTruncate(value)}</span>
      <span className="sr-only">{value}</span>
      {note && <span className="font-sans text-ui text-fg-muted"> · {note}</span>}
    </span>
  );
}
