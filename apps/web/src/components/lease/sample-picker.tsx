"use client";

import { useEffect, useId, useRef, useState } from "react";

import { ExternalLinkIcon, FileCheckIcon } from "@/components/icons";
import { CodeBadge } from "@/components/ui/badge";
import { buttonClass } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { FieldMessage } from "@/components/ui/field";
import { formatDate } from "@/lib/dates";
import type { LeaseRequest } from "@/lib/lease-check";
import { leasePath, type SampleLease } from "@/lib/sample-leases";

/** The lease page while real uploads are off: one of the ten invented leases instead of a
 * file. The chosen lease goes to the checker as its own text, with the jurisdiction and the
 * signing date its header states. */
export function SamplePicker({
  leases,
  onSubmit,
  disabled = false,
  initial,
  focusOnMount = false,
  fetcher = fetch,
}: {
  leases: SampleLease[];
  onSubmit: (request: LeaseRequest) => void;
  disabled?: boolean;
  /** The lease chosen before a failure sent the reader back here. */
  initial?: string | undefined;
  focusOnMount?: boolean;
  fetcher?: typeof fetch;
}) {
  const name = useId();
  const errorId = useId();
  const [chosen, setChosen] = useState<string>(initial ?? "");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const first = useRef<HTMLInputElement>(null);
  const form = useRef<HTMLFormElement>(null);

  // Back on the picker after a check, the focus goes to the lease that was chosen, or the first.
  useEffect(() => {
    if (!focusOnMount) return;
    const checked = form.current?.querySelector<HTMLInputElement>("input:checked");
    (checked ?? first.current)?.focus();
  }, [focusOnMount]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const lease = leases.find((candidate) => candidate.id === chosen);
    if (!lease) {
      setError("Choose a lease to check");
      first.current?.focus();
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const response = await fetcher(leasePath(lease.id));
      if (!response.ok) throw new Error(String(response.status));
      const text = await response.text();
      onSubmit({
        file: new File([text], `${lease.id}.md`, { type: "text/plain" }),
        jurisdiction: lease.jurisdiction.id,
        signedOn: lease.signedOn,
      });
    } catch {
      setError("The lease could not be loaded: check your connection and try again");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      ref={form}
      onSubmit={(event) => void submit(event)}
      noValidate
      className="flex flex-col gap-5"
    >
      <Callout tone="info" title="Uploads are off for now.">
        Until Plumbline can remove names and other personal details from a lease before a model
        reads it, it checks only these ten invented leases, each with clauses written to break the
        law of its jurisdiction.
      </Callout>
      <fieldset
        aria-describedby={error ? errorId : undefined}
        aria-invalid={error ? true : undefined}
        className="flex flex-col gap-2"
      >
        <legend className="mb-2 text-ui font-medium text-fg">Choose a lease to check</legend>
        <ul className="flex flex-col divide-y divide-border-subtle rounded-lg border border-border">
          {leases.map((lease, index) => (
            <li key={lease.id} className="flex items-center gap-3 px-3 py-2.5 hover:bg-bg-hover">
              <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 max-md:min-h-11">
                <input
                  ref={index === 0 ? first : undefined}
                  type="radio"
                  name={name}
                  value={lease.id}
                  checked={chosen === lease.id}
                  onChange={() => {
                    setChosen(lease.id);
                    setError(null);
                  }}
                  disabled={disabled || loading}
                  className="grid size-4 shrink-0 cursor-pointer appearance-none rounded-full border-[1.5px] border-border-control bg-surface checked:border-accent checked:bg-accent checked:shadow-[inset_0_0_0_3px_var(--pl-color-surface)] disabled:cursor-not-allowed"
                />
                <CodeBadge code={lease.jurisdiction.code} />
                <span className="flex min-w-0 flex-col">
                  <span className="text-ui font-medium text-fg">{lease.place}</span>
                  <span className="text-small text-fg-muted">
                    {lease.place === lease.title ? "" : `${lease.title} · `}Signed on{" "}
                    {formatDate(lease.signedOn)}
                  </span>
                </span>
              </label>
              <a
                href={leasePath(lease.id)}
                target="_blank"
                rel="noreferrer"
                className={buttonClass({ variant: "ghost", size: "sm" })}
              >
                <ExternalLinkIcon />
                Read
                <span className="sr-only"> the {lease.place} lease (opens in a new tab)</span>
              </a>
            </li>
          ))}
        </ul>
        {error && <FieldMessage id={errorId} error={error} />}
      </fieldset>
      <div>
        <button
          type="submit"
          disabled={disabled || loading}
          className={buttonClass({ variant: "primary" })}
        >
          <FileCheckIcon />
          {loading ? "Loading the lease…" : "Check this lease"}
        </button>
      </div>
    </form>
  );
}
