import type { AnswerSummary } from "@plumbline/ts-client";
import { useId } from "react";

import { CircleDashedIcon } from "@/components/icons";
import { formatDate } from "@/lib/dates";
import { JURISDICTIONS } from "@/lib/jurisdictions";

/** "Dubai, Spain and Florida": names in the fixed order, joined for prose. */
function names(ids: AnswerSummary["jurisdictions"]): string {
  const named = ids.length > 0 ? JURISDICTIONS.filter((j) => ids.includes(j.id)) : JURISDICTIONS;
  const list = named.map((j) => j.name);
  return list.length > 1 ? `${list.slice(0, -1).join(", ")} and ${list.at(-1)}` : (list[0] ?? "");
}

/** Abstention spec: a designed result in neutral colours, never an error. The stream gives a
 * reason in words but no category, so the title is the general one. */
export function Abstention({ summary }: { summary: AnswerSummary }) {
  const titleId = useId();
  return (
    <section
      aria-labelledby={titleId}
      className="flex flex-col gap-3 rounded-lg border border-dashed border-neutral-border bg-neutral-bg px-4.5 py-4"
    >
      <h2 id={titleId} className="flex items-center gap-2 text-heading-3">
        <CircleDashedIcon size={20} className="shrink-0 text-neutral" />
        {"I couldn't find a statute that answers this."}
      </h2>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 text-ui">
        <dt className="text-fg-muted">Searched</dt>
        <dd>The tenancy statutes of {names(summary.jurisdictions)}</dd>
        <dt className="text-fg-muted">Law as of</dt>
        <dd>{summary.as_of ? formatDate(summary.as_of) : "Today"}</dd>
        {summary.abstain_reason && (
          <>
            <dt className="text-fg-muted">Why</dt>
            <dd>{summary.abstain_reason}</dd>
          </>
        )}
      </dl>
      <div>
        <h3 className="mb-1 text-ui-strong">What you can do</h3>
        <ul className="list-disc pl-4.5 text-body">
          <li>Ask about a property in Dubai, Spain, Colombia or Florida.</li>
          <li>Name the article you have in mind, or describe the situation in more detail.</li>
          <li>
            For advice on your own case, a tenant-rights organisation or a lawyer licensed where the
            property is can help.
          </li>
        </ul>
      </div>
    </section>
  );
}

/** PartialAnswer spec: the part the statutes don't cover, named after the supported part so
 * silence is never read as a "no". */
export function AnswerGap({ reason }: { reason: string | null }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-dashed border-neutral-border bg-neutral-bg px-3.5 py-3 text-body">
      <p className="flex items-center gap-2 text-ui-strong text-neutral">
        <CircleDashedIcon className="shrink-0" />
        Not covered by the statutes I hold
      </p>
      <p>{reason ?? "Part of this question isn't covered by the statutes I hold yet."}</p>
    </div>
  );
}
