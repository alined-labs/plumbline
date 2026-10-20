import path from "node:path";

import { render, screen, waitFor, within } from "@testing-library/react";

import { api } from "@/lib/api";
import { loadEvals, type EvalsData } from "@/lib/evals-files";
import type { OnlineNight } from "@/lib/online";
import { QueryWrapper } from "@/test/query";

import { EvalsView, GATE } from "./evals-view";

const data = loadEvals(path.join(process.cwd(), "src/test/fixtures/evals"));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** The page with the API's tier and the nightly route answered as given; by default the tier
 * is full and the route has no night yet. */
function renderView(
  view: EvalsData = data,
  { tier = "full", nights = [] }: { tier?: string; nights?: OnlineNight[] | "down" } = {},
) {
  vi.spyOn(api, "GET").mockImplementation((async () => ({
    data: { tier, updated_at: null },
    error: undefined,
    response: new Response(),
  })) as unknown as typeof api.GET);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      if (nights === "down") throw new TypeError("Failed to fetch");
      return Response.json(nights);
    }),
  );
  return render(<EvalsView data={view} />, { wrapper: QueryWrapper });
}

const night: OnlineNight = {
  day: "2026-10-23",
  config_name: "A2-claude",
  answered: 42,
  sampled: 5,
  judged: 5,
  faithful: 4,
  faithfulness: 0.8,
  interval_95: [0.376, 0.964],
};

describe("EvalsView", () => {
  it("leads with the default configuration's numbers and their intervals", () => {
    renderView();
    expect(
      screen.getByRole("heading", { name: "The default configuration, A2" }),
    ).toBeInTheDocument();
    const headline = screen.getByRole("group", { name: "Headline numbers for A2" });
    expect(within(headline).getByText("Citation precision")).toBeInTheDocument();
    expect(within(headline).getByText("0.77")).toBeInTheDocument();
    expect(within(headline).getByText("95% CI 0.65–0.87")).toBeInTheDocument();
    expect(within(headline).getByText("p95 latency")).toBeInTheDocument();
    expect(within(headline).getByText("Cost per question")).toBeInTheDocument();
    expect(
      screen.getByText(/development split of 24 questions, run on 21 Oct 2026/),
    ).toBeInTheDocument();
  });

  it("puts every configuration in the retrieval table and only judged runs in the answers table", () => {
    renderView();
    const retrieval = within(screen.getByRole("region", { name: "Retrieval" }));
    expect(retrieval.getAllByRole("rowheader").map((cell) => cell.textContent)).toEqual([
      expect.stringMatching(/^A0/),
      expect.stringMatching(/^A2/),
      expect.stringMatching(/^LC/),
    ]);
    // LC has no search, so its retrieval scores say they were not measured.
    expect(retrieval.getAllByText("not measured")).toHaveLength(5);
    const answers = within(screen.getByRole("region", { name: "Answers" }));
    expect(answers.getAllByRole("rowheader")).toHaveLength(2);
    expect(
      answers.getByRole("columnheader", { name: /False abstention.*lower is better/ }),
    ).toBeInTheDocument();
  });

  it("draws each configuration's score with its interval, says the takeaway and keeps the data", () => {
    render(<EvalsView data={data} />);
    const chart = screen.getByRole("figure", { name: /Recall@5 by configuration/ });
    expect(chart).toHaveTextContent(/A2 scores highest, 0.75/);
    const table = within(chart).getByRole("table", { hidden: true });
    expect(
      within(table)
        .getAllByRole("rowheader", { hidden: true })
        .map((r) => r.textContent),
    ).toEqual(["A0", "A2"]);
  });

  it("says how often a second judge agreed with the first", () => {
    renderView();
    expect(screen.getByText(/A2: a second judge agreed with the first on/)).toHaveTextContent(
      "0.90 of faithfulness verdicts (95% CI 0.70–0.97, 20 answers) and 0.85 of correctness verdicts (95% CI 0.64–0.95, 20 answers).",
    );
  });

  it("marks the per-jurisdiction numbers descriptive and gives each its count", () => {
    renderView();
    expect(screen.getByText("Descriptive")).toBeInTheDocument();
    const table = within(screen.getByRole("region", { name: "Scores by jurisdiction" }));
    expect(table.getByRole("rowheader", { name: /AE-DU\s*Dubai/ })).toBeInTheDocument();
    expect(table.getAllByText("n = 4").length).toBeGreaterThan(0);
  });

  it("reports the judge's rates with their intervals and whether each meets the bar", () => {
    renderView();
    const table = within(screen.getByRole("region", { name: "The judge's accuracy" }));
    expect(table.getByText("0.92")).toBeInTheDocument();
    expect(table.getByText(/46\/50/)).toBeInTheDocument();
    expect(table.getByText("Meets it")).toBeInTheDocument();
    // Correctness's true-negative rate is 38/50 = 0.76, under 0.80.
    expect(table.getByText("Below it")).toBeInTheDocument();
  });

  it("says how the constructed labels were made, and links the method", () => {
    renderView();
    expect(screen.getByText(/one planted error each/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "How they were made" })).toHaveAttribute(
      "href",
      expect.stringMatching(/evals\/calibration\/README\.md$/),
    );
  });

  it("says the judge's accuracy is still to come when there is no table", () => {
    renderView({ ...data, agreement: null });
    expect(screen.queryByRole("region", { name: "The judge's accuracy" })).not.toBeInTheDocument();
    expect(screen.getByText(/Its measured accuracy appears here once/)).toBeInTheDocument();
  });

  it("links the gate's runs and sets each threshold beside the score", () => {
    renderView();
    expect(screen.getByRole("link", { name: "See the gate's runs" })).toHaveAttribute(
      "href",
      GATE.workflow,
    );
    const table = within(screen.getByRole("region", { name: "The gate's thresholds" }));
    expect(table.getByText("at least 0.70")).toBeInTheDocument();
  });

  it("gives every configuration its latency and cost", () => {
    renderView();
    const table = within(
      screen.getByRole("region", { name: "Latency and cost per configuration" }),
    );
    expect(table.getAllByRole("rowheader")).toHaveLength(3);
    expect(table.getAllByText(/^\$/).length).toBeGreaterThan(0);
  });

  it("shows the live site's judged nights, newest first, with their intervals", async () => {
    renderView(data, { nights: [night] });
    const table = await screen.findByRole("region", { name: "Live answers judged each night" });
    expect(within(table).getByRole("rowheader", { name: /23 Oct 2026/ })).toBeInTheDocument();
    expect(within(table).getByText("0.80")).toBeInTheDocument();
    expect(within(table).getByText(/0.38–0.96 · 4\/5/)).toBeInTheDocument();
  });

  it("shows no nights when the route is down, none is judged yet, or the tier is static", async () => {
    for (const options of [
      { nights: "down" as const },
      { nights: [] },
      { nights: [{ ...night, judged: 0, faithfulness: null, interval_95: null }] },
      { nights: [night], tier: "static" },
    ]) {
      const { unmount } = renderView(data, options);
      await waitFor(() => expect(api.GET).toHaveBeenCalled());
      await new Promise((resolve) => setTimeout(resolve, 20));
      expect(screen.queryByRole("heading", { name: "Live answers, night by night" })).toBeNull();
      unmount();
      vi.restoreAllMocks();
    }
  });
});
