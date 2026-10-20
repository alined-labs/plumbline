import { Badge } from "@/components/ui/badge";
import { groupFindings, SEVERITY_INFO, type Finding } from "@/lib/lease";

import { FindingCard } from "./finding-card";

/** The findings in their four groups under headings with counts, most pressing first, with a
 * summary of the counts above. Never a score or a grade for the whole lease. */
export function Findings({ findings }: { findings: readonly Finding[] }) {
  const groups = groupFindings(findings);
  return (
    <div className="flex flex-col gap-6">
      <p className="flex flex-wrap items-center gap-2" aria-label="Summary of findings">
        {groups.map(({ severity, findings: inGroup }) => (
          <Badge key={severity} tone={SEVERITY_INFO[severity].tone}>
            {inGroup.length} {SEVERITY_INFO[severity].summary(inGroup.length)}
          </Badge>
        ))}
      </p>
      {groups.map(({ severity, findings: inGroup }) => (
        <section key={severity} className="flex flex-col gap-3">
          <h3 className="flex items-center gap-2 text-heading-3">
            {SEVERITY_INFO[severity].group}
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-bg-active px-1.5 text-micro font-semibold tabular-nums text-fg-muted">
              {inGroup.length}
            </span>
          </h3>
          <div className="flex flex-col gap-3">
            {inGroup.map((finding) => (
              <FindingCard key={finding.n} finding={finding} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
