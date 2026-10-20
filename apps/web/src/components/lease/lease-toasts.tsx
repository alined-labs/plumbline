"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { useToasts, type ToastHandle } from "@/components/ui/toast";
import { summarize } from "@/lib/lease";
import type { StartedJob } from "@/lib/lease-job";

import { useLeaseJob } from "./lease-job";

const LEASE_PAGE = "/check-lease";

/** "Checking lease · 8 of 14 clauses": the Toast spec's wording for a job in the background. */
function runningLabel(job: StartedJob): string {
  return job.clauses
    ? `Checking lease · ${job.clauses.done} of ${job.clauses.total} clauses`
    : "Checking lease";
}

/** "Lease checked: 4 findings": counted from what the page would show. */
function doneLabel(job: StartedJob): string {
  const { total } = summarize(job.findings);
  return total === 0
    ? "Lease checked: no findings"
    : `Lease checked: ${total} ${total === 1 ? "finding" : "findings"}`;
}

/** Toast spec, the job in the background: while the reader is on another page a running check
 * stays visible as a toast with Cancel, and when it ends the toast says how, with a View
 * action back to the page. On the lease page itself there is no toast: the page shows it. */
export function LeaseToasts() {
  const { job, reset } = useLeaseJob();
  const toasts = useToasts();
  const pathname = usePathname();
  const router = useRouter();
  const away = !pathname.startsWith(LEASE_PAGE);
  const shown = useRef<{ handle: ToastHandle; label: string } | null>(null);
  // The toast manager changes whenever a toast does, so the effect below reads it from here
  // instead of depending on it: updating a toast must not run the effect again.
  const manager = useRef(toasts);
  useEffect(() => {
    manager.current = toasts;
  });

  useEffect(() => {
    const view = { label: "View", onClick: () => router.push(LEASE_PAGE) };
    if (job.status === "running" && away) {
      const label = runningLabel(job);
      const cancel = { label: "Cancel", onClick: reset };
      if (!shown.current) {
        shown.current = { handle: manager.current.job(label, cancel), label };
      } else if (shown.current.label !== label) {
        shown.current.handle.update({ label, action: cancel });
        shown.current.label = label;
      }
      return;
    }
    const toast = shown.current?.handle;
    if (!toast) return;
    shown.current = null;
    // The check ended while the reader was elsewhere: say how, once, and let the toast go.
    if (away && job.status === "done") {
      toast.update({ label: doneLabel(job), action: view, done: true });
    } else if (away && job.status === "failed") {
      toast.update({ label: "The lease check stopped", action: view, done: true });
    } else {
      toast.close();
    }
  }, [job, away, reset, router]);

  return null;
}
