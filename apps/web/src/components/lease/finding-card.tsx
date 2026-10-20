import { InfoIcon } from "@/components/icons";
import { Badge, CodeBadge } from "@/components/ui/badge";
import { jurisdictionInfo } from "@/lib/jurisdictions";
import { SEVERITY_INFO, shownCitations, type Finding } from "@/lib/lease";

/** FindingCard spec: one lease clause beside the statute passage it was checked against, with
 * the verdict and the reason in plain English. The clause is in the lease's own words and
 * language, and the law is quoted in its own, in the serif, so a reader can tell whose words
 * are whose. The two columns stack when the card is narrower than 560px, whatever the screen. */
export function FindingCard({ finding }: { finding: Finding }) {
  const info = SEVERITY_INFO[finding.severity];
  const citations = shownCitations(finding);
  const jurisdictions = [...new Set(citations.map((citation) => citation.ref.jurisdiction))];

  return (
    <article className="@container overflow-hidden rounded-lg border border-border bg-surface">
      <header className="flex flex-wrap items-center gap-x-2.5 gap-y-2 border-b border-border-subtle px-4 py-3">
        <Badge tone={info.tone}>{info.word}</Badge>
        <h4 className="min-w-50 flex-1 text-body font-semibold">{finding.title}</h4>
        {jurisdictions.map((id) => (
          <CodeBadge key={id} code={jurisdictionInfo(id).code} />
        ))}
        <span className="text-small text-fg-muted">Clause {finding.clause_number}</span>
      </header>
      <div className="grid @min-[35rem]:grid-cols-2">
        <section className="flex flex-col gap-2 px-4 py-3.5">
          <h5 className="font-mono text-eyebrow uppercase text-fg-muted">Your lease</h5>
          <p lang={finding.clause_language} className="text-body">
            {finding.clause_text}
          </p>
        </section>
        <section className="flex flex-col gap-3 border-t border-border-subtle px-4 py-3.5 @min-[35rem]:border-l @min-[35rem]:border-t-0">
          {citations.map((citation) => (
            <div key={citation.n} className="flex flex-col gap-2">
              <h5 className="font-mono text-eyebrow uppercase text-fg-muted">
                The law · {citation.label}
              </h5>
              <p lang={citation.language} className="font-serif text-quote-sm">
                <mark className="rounded-xs bg-highlight px-0.5 text-inherit box-decoration-clone">
                  {citation.quote}
                </mark>
              </p>
              {citation.gloss && <p className="text-small text-fg-muted">{citation.gloss}</p>}
            </div>
          ))}
        </section>
      </div>
      <footer className="flex flex-col gap-2 border-t border-border-subtle bg-bg-subtle px-4 py-3">
        <p className="flex gap-2.5 text-body">
          <InfoIcon className="mt-0.5 shrink-0 text-accent-text" />
          <span>{finding.why}</span>
        </p>
        <p className="pl-6.5 text-small text-fg-muted">
          Confidence <span className="font-mono tabular-nums">{finding.confidence.toFixed(2)}</span>
        </p>
      </footer>
    </article>
  );
}
