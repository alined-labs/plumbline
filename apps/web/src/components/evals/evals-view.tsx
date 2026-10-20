import type { ReactNode } from "react";

import { Badge, CodeBadge } from "@/components/ui/badge";
import { Metric, MetricGrid } from "@/components/ui/metric";
import { IntervalChart } from "@/components/ui/interval-chart";
import { RowHead, Table, Td, Th, Tr } from "@/components/ui/table";
import { formatDate } from "@/lib/dates";
import {
  ANSWER_METRICS,
  estimate,
  formatInterval,
  formatLatency,
  formatScore,
  formatUsd,
  groupMeans,
  baseConfig,
  chartPoints,
  headlineRun,
  HEADLINE_METRICS,
  METRICS,
  RETRIEVAL_METRICS,
  runCost,
  secondJudge,
  takeaway,
  type Agreement,
  type EvalRun,
  type MetricName,
  type Rate,
} from "@/lib/evals";
import type { EvalsData } from "@/lib/evals-files";

import { OnlineNightsLazy as OnlineNights } from "./online-nights-lazy";

const REPO = "https://github.com/alined-labs/plumbline";

/** The CI gate's workflow, and the run where it blocked a change that made answers worse.
 * The red run's address is filled in once Lane A has made it. */
export const GATE = {
  workflow: `${REPO}/actions/workflows/eval-gate.yml`,
  redRun: null as string | null,
};

/** What each configuration adds, in a few words (evals/configs holds the whole definition). */
const CONFIGS: Record<string, string> = {
  A0: "Naive baseline: fixed chunks, dense search",
  A1: "Article-aware chunks",
  A2: "Hybrid search: dense and keyword, fused",
  A3: "A2 with the local reranker",
  A4: "A3 with a context header per chunk",
  A5: "A4 with written contextual headers",
  A6: "A5 with the cross-lingual rewrite",
  E1: "BGE-M3 embeddings",
  R1: "Cohere reranker",
  LC: "Long context: the whole law, no search",
};

/** A configuration's words: its own, or its base's with who writes the answers. */
function describe(name: string): string | undefined {
  const { base, claude } = baseConfig(name);
  const words = CONFIGS[base];
  if (!words) return undefined;
  return claude ? `${words}, answered by Claude Sonnet as the public site is` : words;
}

/** Per-jurisdiction columns: one retrieval number and the answer numbers that matter most. */
const GROUP_METRICS = [
  "recall@5",
  "citation_precision",
  "correctness",
  "abstention_accuracy",
] as const satisfies readonly MetricName[];

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h2 id={id} className="text-heading-2">
        {title}
      </h2>
      {children}
    </section>
  );
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className="text-accent underline underline-offset-2 hover:text-accent-hover">
      {children}
    </a>
  );
}

/** A dash that says "not measured" to a screen reader. */
function NotMeasured() {
  return (
    <>
      <span aria-hidden="true" className="text-fg-subtle">
        –
      </span>
      <span className="sr-only">not measured</span>
    </>
  );
}

/** A score over its interval, both in tabular numerals. */
function ScoreCell({ run, name }: { run: EvalRun; name: MetricName }) {
  const value = estimate(run.summary, name);
  if (!value) return <NotMeasured />;
  const interval = formatInterval(value.low, value.high);
  return (
    <span className="flex flex-col items-end whitespace-nowrap">
      <span>{formatScore(value.value)}</span>
      {interval && (
        <span className="font-mono text-code-sm text-fg-subtle">
          <span className="sr-only">95% interval </span>
          {interval}
        </span>
      )}
    </span>
  );
}

function ConfigHead({ run }: { run: EvalRun }) {
  return (
    <RowHead>
      <span className="block">{run.config_name}</span>
      {describe(run.config_name) && (
        <span className="block min-w-48 text-small font-normal text-fg-muted">
          {describe(run.config_name)}
        </span>
      )}
    </RowHead>
  );
}

function MetricsTable({
  label,
  runs,
  metrics,
}: {
  label: string;
  runs: EvalRun[];
  metrics: readonly MetricName[];
}) {
  // A column nobody measured says nothing; a row where nothing applies keeps its dashes, so a
  // retrieval-only run reads as such.
  const shown = metrics.filter((name) => runs.some((run) => estimate(run.summary, name)));
  if (shown.length === 0) return null;
  return (
    <Table label={label} caption={`${label}: each score with its 95% interval below it.`}>
      <thead>
        <tr>
          <Th>Configuration</Th>
          {shown.map((name) => (
            <Th key={name} num>
              {METRICS[name].label}
              {METRICS[name].better === "lower" && (
                <span className="sr-only"> (lower is better)</span>
              )}
            </Th>
          ))}
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <Tr key={run.run_id}>
            <ConfigHead run={run} />
            {shown.map((name) => (
              <Td key={name} num>
                <ScoreCell run={run} name={name} />
              </Td>
            ))}
          </Tr>
        ))}
      </tbody>
    </Table>
  );
}

function Headline({ run }: { run: EvalRun }) {
  const cost = runCost(run);
  return (
    <MetricGrid label={`Headline numbers for ${run.config_name}`}>
      {HEADLINE_METRICS.map((name) => {
        const value = estimate(run.summary, name);
        const interval = value && formatInterval(value.low, value.high);
        return (
          <Metric
            key={name}
            label={METRICS[name].label}
            value={value ? formatScore(value.value) : "–"}
            detail={value ? (interval ? `95% CI ${interval}` : `n = ${value.n}`) : "Not measured"}
          />
        );
      })}
      <Metric
        label="p95 latency"
        value={cost.p95Ms === null ? "–" : formatLatency(cost.p95Ms)}
        detail={cost.p50Ms === null ? "Not measured" : `p50 ${formatLatency(cost.p50Ms)}`}
      />
      <Metric
        label="Cost per question"
        value={cost.perQuestionUsd === null ? "–" : formatUsd(cost.perQuestionUsd)}
        detail={cost.totalUsd === null ? "Not measured" : `${formatUsd(cost.totalUsd)} for the run`}
      />
    </MetricGrid>
  );
}

/** How far a second judge, of another model, agreed with the first on the same answers: the
 * check that a judge's verdicts are not its own family's taste. */
/** One metric across configurations as dots with their intervals, when two or more measured it. */
function MetricChart({
  runs,
  metric,
  threshold,
}: {
  runs: EvalRun[];
  metric: MetricName;
  threshold: number | undefined;
}) {
  const points = chartPoints(runs, metric);
  if (points.length < 2) return null;
  return (
    <IntervalChart
      title={`${METRICS[metric].label} by configuration`}
      caption={takeaway(points, metric)}
      points={points}
      threshold={threshold}
    />
  );
}

function SecondJudge({ run }: { run: EvalRun }) {
  const rows = secondJudge(run);
  if (rows.length === 0) return null;
  return (
    <p className="text-small text-fg-muted">
      {run.config_name}: a second judge agreed with the first on{" "}
      {rows.map(({ criterion, agreement }, index) => {
        const interval = formatInterval(agreement.low, agreement.high);
        return (
          <span key={criterion}>
            {index > 0 && (index === rows.length - 1 ? " and " : ", ")}
            {formatScore(agreement.value)} of {METRICS[criterion].label.toLowerCase()} verdicts
            {interval && ` (95% CI ${interval}, ${agreement.n} answers)`}
          </span>
        );
      })}
      .
    </p>
  );
}

function ByJurisdiction({ run }: { run: EvalRun }) {
  const rows = groupMeans(run, GROUP_METRICS);
  const shown = GROUP_METRICS.filter((name) => rows.some((row) => row.means[name]));
  if (rows.length === 0 || shown.length === 0) return null;
  return (
    <>
      <p className="text-fg-muted">
        <Badge tone="neutral">Descriptive</Badge> Each group holds a few dozen questions at most, so
        its interval would be too wide to rank one jurisdiction above another. These are plain means
        of {run.config_name}&apos;s scores, with the number of questions each is taken over.
      </p>
      <Table
        label="Scores by jurisdiction"
        caption={`Mean scores of ${run.config_name} by jurisdiction, descriptive only, with the number of questions behind each.`}
      >
        <thead>
          <tr>
            <Th>Group</Th>
            <Th num>Questions</Th>
            {shown.map((name) => (
              <Th key={name} num>
                {METRICS[name].label}
              </Th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ group, items, means }) => (
            <Tr key={group.prefix}>
              <RowHead>
                <span className="inline-flex items-center gap-2">
                  {group.code && <CodeBadge code={group.code} />}
                  {group.name}
                </span>
              </RowHead>
              <Td num>{items}</Td>
              {shown.map((name) => {
                const mean = means[name];
                return (
                  <Td key={name} num>
                    {mean ? (
                      <span className="flex flex-col items-end whitespace-nowrap">
                        <span>{formatScore(mean.value)}</span>
                        <span className="font-mono text-code-sm text-fg-subtle">n = {mean.n}</span>
                      </span>
                    ) : (
                      <NotMeasured />
                    )}
                  </Td>
                );
              })}
            </Tr>
          ))}
        </tbody>
      </Table>
    </>
  );
}

function RateCell({ rate }: { rate: Rate }) {
  if (rate.total === 0) return <NotMeasured />;
  return (
    <span className="flex flex-col items-end whitespace-nowrap">
      <span>{formatScore(rate.hits / rate.total)}</span>
      <span className="font-mono text-code-sm text-fg-subtle">
        <span className="sr-only">95% interval </span>
        {formatInterval(rate.low, rate.high)} · {rate.hits}/{rate.total}
      </span>
    </span>
  );
}

const LABELS = { constructed: "Constructed labels", human: "The maintainer's labels" } as const;

function JudgeTable({ agreement }: { agreement: Agreement }) {
  const { bar } = agreement;
  return (
    <>
      <p className="text-fg-muted">
        The judge ({agreement.judge_model}) is scored against answers whose verdict is known. The
        true-positive rate is the share of good answers it passes; the true-negative rate, the share
        of flawed answers it fails. Both must reach {formatScore(bar)} before its verdicts count.
      </p>
      {agreement.sets.some((set) => set.labels === "constructed") && (
        <p className="text-fg-muted">
          The constructed labels are answers built for the test from development questions: correct
          ones, and copies with one planted error each, so their verdict is known without a person
          grading them.{" "}
          <ExternalLink href={`${REPO}/blob/main/evals/calibration/README.md`}>
            How they were made
          </ExternalLink>
          .
        </p>
      )}
      <Table
        label="The judge's accuracy"
        caption="The judge's true-positive and true-negative rates per criterion, with 95% Wilson intervals and counts."
      >
        <thead>
          <tr>
            <Th>Criterion</Th>
            <Th>Labels</Th>
            <Th num>True-positive rate</Th>
            <Th num>True-negative rate</Th>
            <Th>Bar of {formatScore(bar)}</Th>
          </tr>
        </thead>
        <tbody>
          {agreement.sets.flatMap((set) =>
            set.criteria.map(({ criterion, tpr, tnr }) => {
              const meets = [tpr, tnr].every((r) => r.total > 0 && r.hits / r.total >= bar);
              return (
                <Tr key={`${set.labels}-${criterion}`}>
                  <RowHead>{METRICS[criterion as MetricName]?.label ?? criterion}</RowHead>
                  <Td>
                    <span className="block">{LABELS[set.labels]}</span>
                    <span className="block min-w-56 text-small text-fg-muted">
                      {set.description}
                    </span>
                  </Td>
                  <Td num>
                    <RateCell rate={tpr} />
                  </Td>
                  <Td num>
                    <RateCell rate={tnr} />
                  </Td>
                  <Td>
                    {meets ? (
                      <Badge tone="success">Meets it</Badge>
                    ) : (
                      <Badge tone="warning">Below it</Badge>
                    )}
                  </Td>
                </Tr>
              );
            }),
          )}
        </tbody>
      </Table>
    </>
  );
}

function Gate({
  run,
  thresholds,
}: {
  run: EvalRun | undefined;
  thresholds: EvalsData["thresholds"];
}) {
  const names = (Object.keys(thresholds) as MetricName[]).filter((name) => METRICS[name]);
  return (
    <>
      <p>
        Every pull request runs the retrieval metrics on the golden questions and judges a sample of
        30 answers. A change that takes a score below its threshold cannot merge.{" "}
        {GATE.redRun ? (
          <ExternalLink href={GATE.redRun}>
            See the gate block a change that made answers worse
          </ExternalLink>
        ) : (
          <ExternalLink href={GATE.workflow}>See the gate&apos;s runs</ExternalLink>
        )}
        .
      </p>
      {names.length > 0 && (
        <Table
          label="The gate's thresholds"
          caption="Each gated metric's threshold beside the headline configuration's score."
        >
          <thead>
            <tr>
              <Th>Metric</Th>
              <Th num>Threshold</Th>
              <Th num>{run ? `${run.config_name} scores` : "Score"}</Th>
            </tr>
          </thead>
          <tbody>
            {names.map((name) => {
              const threshold = thresholds[name] ?? 0;
              return (
                <Tr key={name}>
                  <RowHead>{METRICS[name].label}</RowHead>
                  <Td num>
                    {METRICS[name].better === "lower" ? "at most " : "at least "}
                    {formatScore(threshold)}
                  </Td>
                  <Td num>{run ? <ScoreCell run={run} name={name} /> : <NotMeasured />}</Td>
                </Tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </>
  );
}

function CostTable({ runs }: { runs: EvalRun[] }) {
  return (
    <Table
      label="Latency and cost per configuration"
      caption="Each configuration's latency per question and what its model calls cost."
    >
      <thead>
        <tr>
          <Th>Configuration</Th>
          <Th num>p50 latency</Th>
          <Th num>p95 latency</Th>
          <Th num>Cost per question</Th>
          <Th num>Cost of the run</Th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => {
          const cost = runCost(run);
          return (
            <Tr key={run.run_id}>
              <ConfigHead run={run} />
              <Td num>{cost.p50Ms === null ? <NotMeasured /> : formatLatency(cost.p50Ms)}</Td>
              <Td num>{cost.p95Ms === null ? <NotMeasured /> : formatLatency(cost.p95Ms)}</Td>
              <Td num>
                {cost.perQuestionUsd === null ? <NotMeasured /> : formatUsd(cost.perQuestionUsd)}
              </Td>
              <Td num>{cost.totalUsd === null ? <NotMeasured /> : formatUsd(cost.totalUsd)}</Td>
            </Tr>
          );
        })}
      </tbody>
    </Table>
  );
}

/** The evaluation page: the headline configuration's numbers, every configuration with its
 * intervals, the jurisdictions (descriptive), the judge's own accuracy, the CI gate and what
 * it all costs. Each section waits quietly for its file. */
export function EvalsView({ data }: { data: EvalsData }) {
  const { runs, agreement, thresholds } = data;
  const headline = headlineRun(runs);
  const times = runs.map((run) => Date.parse(run.created_at));
  const latest = times.length ? new Date(Math.max(...times)) : null;
  const questions = Math.max(0, ...runs.map((run) => run.n_items));

  return (
    <article className="flex flex-col gap-10 text-body">
      <header className="flex flex-col gap-3">
        <h1 className="text-heading-1">Evaluation</h1>
        <p className="text-body-lg">
          How often Plumbline finds the right article, cites it, answers correctly and declines when
          it should, measured on a public set of tenancy questions.
        </p>
        <p className="text-fg-muted">
          These are results on the development split
          {questions > 0 && <> of {questions} questions</>}
          {latest && <>, run on {formatDate(latest)}</>}. The held-out test split is run once, for
          the release. Every score carries its 95% interval: a Wilson interval for a share of
          questions, a bootstrap over questions for a mean.
        </p>
      </header>

      {headline && (
        <Section id="headline" title={`The default configuration, ${headline.config_name}`}>
          {describe(headline.config_name) && (
            <p className="text-fg-muted">{describe(headline.config_name)}.</p>
          )}
          <Headline run={headline} />
        </Section>
      )}

      <Section id="configurations" title="Every configuration">
        <p className="text-fg-muted">
          From A0 to A6 each configuration adds one thing to the one before it, so the difference
          between two neighbouring rows is that change&apos;s effect, within the intervals shown. LC
          is the long-context baseline: no search, the whole law in one prompt.
        </p>
        <h3 className="text-heading-3">Finding the right article</h3>
        <MetricChart runs={runs} metric="recall@5" threshold={thresholds["recall@5"]} />
        <MetricsTable label="Retrieval" runs={runs} metrics={RETRIEVAL_METRICS} />
        <h3 className="text-heading-3">Answering</h3>
        <MetricChart
          runs={runs.filter((run) => run.judged)}
          metric="correctness"
          threshold={thresholds.correctness}
        />
        <MetricsTable
          label="Answers"
          runs={runs.filter((run) => run.judged)}
          metrics={ANSWER_METRICS}
        />
        {runs
          .filter((run) => run.judged)
          .map((run) => (
            <SecondJudge key={run.run_id} run={run} />
          ))}
      </Section>

      {headline && (
        <Section id="jurisdictions" title="By jurisdiction">
          <ByJurisdiction run={headline} />
        </Section>
      )}

      <Section id="judge" title="How far the judge can be trusted">
        {agreement ? (
          <JudgeTable agreement={agreement} />
        ) : (
          <p className="text-fg-muted">
            Faithfulness and correctness are judged by a model of a different family from the one
            that answers. Its measured accuracy appears here once it has been checked against
            answers whose verdict is known.
          </p>
        )}
      </Section>

      <OnlineNights />

      <Section id="gate" title="The gate on every change">
        <Gate run={headline} thresholds={thresholds} />
      </Section>

      <Section id="cost" title="Latency and cost">
        <p className="text-fg-muted">
          Per question over the whole run, as each results file records them: the model calls&apos;
          own time and their price per token.
        </p>
        <CostTable runs={runs} />
      </Section>

      <p className="text-small text-fg-muted">
        Every number here is rebuilt from the files in{" "}
        <ExternalLink href={`${REPO}/tree/main/evals`}>evals/</ExternalLink> with{" "}
        <code className="font-mono text-code-sm">make reproduce</code>, which replays the recorded
        model calls.
      </p>
    </article>
  );
}
