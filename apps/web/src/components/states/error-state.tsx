"use client";

import { useState } from "react";

import { CopyIcon, OctagonAlertIcon, RotateCwIcon } from "@/components/icons";
import { buttonClass } from "@/components/ui/button";
import { formatDateTime } from "@/lib/dates";

/** ErrorState spec: a whole view that failed. The first sentence of the body is bold and
 * carries the fix; the ID and time are what a reader quotes when they report it. */
export function ErrorState({
  title,
  lead,
  body,
  errorId,
  at,
  onRetry,
  retryLabel = "Try again",
  headingLevel = 1,
}: {
  title: string;
  lead: string;
  body?: string;
  errorId: string;
  at: Date;
  onRetry?: () => void;
  /** The action's words when "Try again" is not what it does ("Choose another file"). */
  retryLabel?: string;
  /** 2 when the page around it already has its h1. */
  headingLevel?: 1 | 2;
}) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  const [copied, setCopied] = useState(false);
  const stamp = `err ${errorId} · ${formatDateTime(at)}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(stamp);
      setCopied(true);
    } catch {
      // Clipboard access can be refused; the ID stays on screen to copy by hand.
    }
  }

  return (
    <div
      role="alert"
      className="mx-auto flex max-w-115 flex-col items-center gap-3 py-12 text-center"
    >
      <span className="flex size-10 items-center justify-center rounded-full bg-danger-bg text-danger">
        <OctagonAlertIcon size={20} />
      </span>
      <Heading className="text-heading-2">{title}</Heading>
      <p className="text-body text-fg-muted">
        <strong className="font-semibold text-fg">{lead}</strong>
        {body && ` ${body}`}
      </p>
      <div className="flex flex-wrap justify-center gap-3">
        {onRetry && (
          <button type="button" onClick={onRetry} className={buttonClass({ variant: "primary" })}>
            <RotateCwIcon />
            {retryLabel}
          </button>
        )}
        <button type="button" onClick={copy} className={buttonClass()}>
          <CopyIcon />
          {copied ? "Error ID copied" : "Copy error ID"}
        </button>
      </div>
      <span className="font-mono text-code-sm text-fg-subtle">{stamp}</span>
    </div>
  );
}
