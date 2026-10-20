"use client";

import { useEffect, useRef, useState } from "react";

import { UploadIcon } from "@/components/icons";
import { ErrorState } from "@/components/states/error-state";
import { buttonClass } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { ConfirmDialog } from "@/components/ui/dialog";
import { localErrorId } from "@/lib/error-id";
import { failureCopy, showsOnForm } from "@/lib/lease-failures";
import type { JobFailure, StartedJob } from "@/lib/lease-job";
import { announcement } from "@/lib/lease-steps";
import { markNoticeSeen, noticeSeen } from "@/lib/lease-notice";
import type { UploadValues } from "@/lib/lease-upload";
import type { SampleLease } from "@/lib/sample-leases";

import { FileProgress } from "./file-progress";
import { Findings } from "./findings";
import { useLeaseJob } from "./lease-job";
import { SamplePicker } from "./sample-picker";
import { UploadForm } from "./upload-form";

/** The lease page's working part: the form, then a check moving through its steps with the
 * findings arriving, then the findings; or the way a failure is worded. The redaction notice
 * comes before the first upload of a session. With `samples`, real uploads are off and the
 * reader picks an invented lease instead, which needs no redaction notice: nothing in it is
 * anyone's. */
export function LeaseCheck({ samples }: { samples?: SampleLease[] | undefined } = {}) {
  const { job, request, start, retry, reset } = useLeaseJob();
  const [waiting, setWaiting] = useState<UploadValues | null>(null);
  // True once the reader has left a check for the form, which is then where the focus goes: the
  // button they pressed is gone.
  const [returned, setReturned] = useState(false);

  function leave() {
    setReturned(true);
    reset();
  }

  function submit(values: UploadValues) {
    if (noticeSeen()) start(values);
    else setWaiting(values);
  }

  const onForm = job.status === "idle" || (job.status === "failed" && showsOnForm(job.failure));
  return (
    <div className="flex flex-col gap-6">
      {onForm ? (
        <>
          {job.status === "failed" && <FormNotice failure={job.failure} />}
          {samples ? (
            <SamplePicker
              key={job.status === "failed" ? "again" : "first"}
              leases={samples}
              initial={
                job.status === "failed" ? request?.file.name.replace(/\.md$/, "") : undefined
              }
              onSubmit={start}
              focusOnMount={returned || job.status === "failed"}
              disabled={job.status === "failed" && job.failure.code === "lease_checks_paused"}
            />
          ) : (
            <UploadForm
              // A failure that sends the reader back to the form keeps their file and answers.
              key={job.status === "failed" ? "again" : "first"}
              onSubmit={submit}
              initial={job.status === "failed" ? (request ?? undefined) : undefined}
              focusJurisdiction={
                job.status === "failed" && job.failure.code === "jurisdiction_unknown"
              }
              focusOnMount={returned || job.status === "failed"}
              disabled={job.status === "failed" && job.failure.code === "lease_checks_paused"}
            />
          )}
        </>
      ) : (
        <Run job={job} onRetry={retry} onReset={leave} picking={samples !== undefined} />
      )}
      <p role="status" className="sr-only">
        {announcement(job)}
      </p>
      <ConfirmDialog
        open={waiting !== null}
        onOpenChange={(open) => {
          if (!open) setWaiting(null);
        }}
        title="Before you upload a lease"
        confirm={{ label: "Upload a lease", icon: <UploadIcon /> }}
        onConfirm={() => {
          markNoticeSeen();
          if (waiting) start(waiting);
          setWaiting(null);
        }}
      >
        <p>
          Plumbline removes names, ID numbers, addresses and account details from the lease before
          any model reads it.
        </p>
        <p>
          The check is legal information, not legal advice. For a decision about your lease, talk to
          a lawyer licensed where the property is.
        </p>
      </ConfirmDialog>
    </div>
  );
}

/** The demo's own limits and the fix for a missing jurisdiction: a callout above the form,
 * which stays, instead of a page that broke. */
function FormNotice({ failure }: { failure: JobFailure }) {
  const [at] = useState(() => new Date());
  const copy = failureCopy(failure, at);
  return (
    <Callout
      tone={failure.code === "lease_checks_paused" ? "info" : "warning"}
      title={copy.title.endsWith("?") ? copy.title : `${copy.title}.`}
    >
      {copy.lead} {copy.body}
    </Callout>
  );
}

function Run({
  job,
  onRetry,
  onReset,
  picking,
}: {
  job: StartedJob;
  onRetry: () => void;
  onReset: () => void;
  /** The reader picks an invented lease rather than uploading a file. */
  picking: boolean;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const failed = job.status === "failed";
  // The button that started the check is gone, so focus goes to what replaced it; and a failure
  // is where the reader needs to be.
  useEffect(() => {
    heading.current?.focus();
  }, [failed]);

  if (job.status === "failed" && job.findings.length === 0) {
    return (
      <FailureState failure={job.failure} onRetry={onRetry} onReset={onReset} picking={picking} />
    );
  }
  const title =
    job.status === "running" ? "Checking your lease" : failed ? "Findings so far" : "Findings";
  return (
    <section aria-labelledby="run-title" className="flex flex-col gap-4">
      <h2 id="run-title" ref={heading} tabIndex={-1} className="text-heading-2 outline-none">
        {title}
      </h2>
      <FileProgress job={job} />
      {job.status === "failed" && <StoppedNotice failure={job.failure} onRetry={onRetry} />}
      {job.status === "running" && (
        <div>
          <button type="button" onClick={onReset} className={buttonClass({ size: "sm" })}>
            Cancel
          </button>
        </div>
      )}
      {job.findings.length > 0 ? (
        <Findings findings={job.findings} />
      ) : job.status === "running" ? (
        <p className="text-small text-fg-muted">Findings appear here as each clause is checked.</p>
      ) : job.status === "done" ? (
        <Callout tone="info" title="No findings.">
          Plumbline found no clause that conflicts with the statutes it holds. That is not a clean
          bill of health: it only checks the clauses it can match to an article.
        </Callout>
      ) : null}
      {job.status === "done" && (
        <div>
          <button type="button" onClick={onReset} className={buttonClass()}>
            <UploadIcon />
            Check another lease
          </button>
        </div>
      )}
    </section>
  );
}

/** A check that stopped after some findings: they stay, with what happened and Try again. */
function StoppedNotice({ failure, onRetry }: { failure: JobFailure; onRetry: () => void }) {
  const [at] = useState(() => new Date());
  return (
    <Callout
      tone="danger"
      title="The check stopped."
      action={
        <button type="button" onClick={onRetry} className={buttonClass({ size: "sm" })}>
          Try again
        </button>
      }
    >
      {failureCopy(failure, at).lead}
    </Callout>
  );
}

/** A check that failed before it had any findings: the whole view says what happened and what
 * to do (ErrorState spec), with an ID the reader can quote. */
function FailureState({
  failure,
  onRetry,
  onReset,
  picking,
}: {
  failure: JobFailure;
  onRetry: () => void;
  onReset: () => void;
  picking: boolean;
}) {
  const [at] = useState(() => new Date());
  const [errorId] = useState(localErrorId);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  const copy = failureCopy(failure, at);
  return (
    <div ref={ref} tabIndex={-1} className="outline-none">
      <ErrorState
        headingLevel={2}
        title={copy.title}
        lead={copy.lead}
        body={copy.body}
        errorId={errorId}
        at={at}
        onRetry={
          copy.next === "retry" ? onRetry : copy.next === "choose-file" ? onReset : undefined
        }
        retryLabel={
          copy.next === "choose-file" ? `Choose another ${picking ? "lease" : "file"}` : "Try again"
        }
        retryIcon={copy.next === "choose-file" && !picking ? <UploadIcon /> : undefined}
      />
    </div>
  );
}
