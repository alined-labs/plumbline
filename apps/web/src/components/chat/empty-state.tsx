import type { Jurisdiction } from "@plumbline/ts-client";

import { CodeBadge } from "@/components/ui/badge";
import { isIndexed, UNINDEXED } from "@/lib/coverage";
import { jurisdictionInfo } from "@/lib/jurisdictions";

const EXAMPLES: { jurisdiction: Jurisdiction; question: string }[] = [
  {
    jurisdiction: "dubai",
    question: "How much notice does my landlord need to evict me when the lease ends?",
  },
  {
    jurisdiction: "spain",
    question: "What is the minimum length of a residential lease in Spain?",
  },
  {
    jurisdiction: "colombia",
    question: "How much can my landlord in Bogotá raise the rent each year?",
  },
  { jurisdiction: "florida", question: "How long does my landlord have to return my deposit?" },
];

/** EmptyState spec: the first screen of a new question. What Plumbline covers, in one
 * sentence, and one example per jurisdiction; choosing one asks it in that jurisdiction. */
export function EmptyState({
  onExample,
  unindexed = UNINDEXED,
}: {
  onExample: (question: string, jurisdiction: Jurisdiction) => void;
  /** Jurisdictions the live site has not indexed yet: no example is offered for them. */
  unindexed?: readonly Jurisdiction[];
}) {
  const examples = EXAMPLES.filter(({ jurisdiction }) => isIndexed(jurisdiction, unindexed));
  const pending = unindexed.map((id) => jurisdictionInfo(id).name);
  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <h2 className="text-heading-1">What do you want to know about your lease?</h2>
      <p className="text-body text-fg-muted">
        Plumbline answers from the tenancy statutes of Dubai, Spain, Colombia and Florida, and cites
        the passage behind every claim.
        {pending.length > 0 &&
          ` ${pending.join(" and ")}'s statutes join shortly; until then Plumbline declines questions on ${pending.length > 1 ? "them" : "it"}.`}
      </p>
      <ul aria-label="Example questions" className="grid w-full gap-2 text-left sm:grid-cols-2">
        {examples.map(({ jurisdiction, question }) => (
          <li key={jurisdiction}>
            <button
              type="button"
              onClick={() => onExample(question, jurisdiction)}
              className="flex h-full w-full flex-col items-start gap-1.5 rounded-lg border border-border bg-surface px-3.5 py-3 text-left text-ui text-fg hover:border-border-strong hover:bg-bg-hover"
            >
              <CodeBadge code={jurisdictionInfo(jurisdiction).code} />
              {question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
