"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
} from "react";

import type { LeaseRequest, Transport } from "@/lib/lease-check";
import { IDLE, reduceJob, type JobAction, type JobFailure, type LeaseJob } from "@/lib/lease-job";

type LeaseJobApi = {
  job: LeaseJob;
  /** The request of the check that is running or ended, so a form can keep the file. */
  request: LeaseRequest | null;
  start: (request: LeaseRequest) => void;
  /** The same request again, after a failure. */
  retry: () => void;
  /** Stops the check and goes back to the form. */
  reset: () => void;
};

const LeaseJobContext = createContext<LeaseJobApi | null>(null);

/** A LeaseFailure carries a code, its words and any wait. Anything else (a chunk that would not
 * load, a bug) is the checker not answering. Read by shape, so this file needs nothing from
 * the transport until a check starts. */
function failureOf(error: unknown): JobFailure {
  if (error instanceof Error && "code" in error && typeof error.code === "string") {
    const wait =
      "retryAfter" in error && typeof error.retryAfter === "number" ? error.retryAfter : undefined;
    return { code: error.code, message: error.message, retryAfter: wait };
  }
  return { code: "unavailable", message: "The lease checker didn't answer." };
}

// One check from upload to its last event. The reader's cancel is the signal: after it nothing
// more is dispatched, so a check that was left cannot touch the next one. The transport is
// loaded here, on the first check, because this provider is in every page's layout and most
// readers never check a lease.
async function run(request: LeaseRequest, transport: Transport, dispatch: Dispatch<JobAction>) {
  const { signal } = transport;
  dispatch({ type: "start", file: { name: request.file.name, size: request.file.size } });
  try {
    const lease = await import("@/lib/lease-check");
    const id = await lease.startLeaseCheck(request, transport);
    for await (const event of lease.leaseEvents(id, transport)) {
      if (signal?.aborted) return;
      dispatch({ type: "event", event });
    }
  } catch (error) {
    if (signal?.aborted) return;
    dispatch({ type: "fail", failure: failureOf(error) });
  }
}

/** The lease check lives above the pages, so it goes on while the reader looks at another one.
 * Only the findings the checker returns are kept, in memory: nothing of a lease is stored in
 * the browser. `transport` lets a test answer in place of the API. */
export function LeaseJobProvider({
  children,
  transport,
}: {
  children: ReactNode;
  transport?: Transport;
}) {
  const [job, dispatch] = useReducer(reduceJob, IDLE);
  const [request, setRequest] = useState<LeaseRequest | null>(null);
  const running = useRef<AbortController | null>(null);

  const start = useCallback(
    (next: LeaseRequest) => {
      running.current?.abort();
      const cancel = new AbortController();
      running.current = cancel;
      setRequest(next);
      void run(next, { ...transport, signal: cancel.signal }, dispatch);
    },
    [transport],
  );
  const retry = useCallback(() => {
    if (request) start(request);
  }, [request, start]);
  const reset = useCallback(() => {
    running.current?.abort();
    dispatch({ type: "reset" });
  }, []);

  const api = useMemo(
    () => ({ job, request, start, retry, reset }),
    [job, request, start, retry, reset],
  );
  return <LeaseJobContext.Provider value={api}>{children}</LeaseJobContext.Provider>;
}

export function useLeaseJob(): LeaseJobApi {
  const api = useContext(LeaseJobContext);
  if (!api) throw new Error("useLeaseJob needs a LeaseJobProvider");
  return api;
}
