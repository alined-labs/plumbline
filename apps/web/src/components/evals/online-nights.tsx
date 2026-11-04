"use client";

import { useQuery } from "@tanstack/react-query";

import { RowHead, Table, Td, Th, Tr } from "@/components/ui/table";
import { formatDate } from "@/lib/dates";
import { formatInterval, formatScore } from "@/lib/evals";
import { judgedNights, onlineQuery } from "@/lib/online";
import { useDemoMode } from "@/lib/tier";

/** The live site's answers, judged night by night, beside the offline numbers. Nothing at all
 * when the route fails, has no judged night yet, or the demo is the static tier. */
export function OnlineNights() {
  const mode = useDemoMode();
  const { data } = useQuery({ ...onlineQuery(), enabled: mode === "live" });
  const nights = data ? judgedNights(data) : [];
  if (mode !== "live" || nights.length === 0) return null;
  return (
    <section aria-labelledby="online" className="flex flex-col gap-3">
      <h2 id="online" className="text-heading-2">
        Live answers, night by night
      </h2>
      <p className="text-fg-muted">
        Each night a sample of the previous day&apos;s answers on this site is judged for
        faithfulness to its sources, the same way as the benchmark&apos;s. No question or answer is
        kept for this, only the counts.
      </p>
      <Table
        label="Live answers judged each night"
        caption="Each night's share of sampled live answers judged faithful, with its 95% interval and counts."
      >
        <thead>
          <tr>
            <Th>Night</Th>
            <Th num>Answered</Th>
            <Th num>Judged</Th>
            <Th num>Faithfulness</Th>
          </tr>
        </thead>
        <tbody>
          {nights.map((night) => (
            <Tr key={night.day}>
              <RowHead>
                <span className="block">{formatDate(night.day)}</span>
                <span className="block text-small font-normal text-fg-muted">
                  {night.config_name}
                </span>
              </RowHead>
              <Td num>{night.answered}</Td>
              <Td num>{night.judged}</Td>
              <Td num>
                <span className="flex flex-col items-end whitespace-nowrap">
                  <span>{formatScore(night.faithfulness ?? 0)}</span>
                  {night.interval_95 && (
                    <span className="font-mono text-code-sm text-fg-subtle">
                      <span className="sr-only">95% interval </span>
                      {formatInterval(night.interval_95[0], night.interval_95[1])} ·{" "}
                      {night.faithful}/{night.judged}
                    </span>
                  )}
                </span>
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </section>
  );
}
