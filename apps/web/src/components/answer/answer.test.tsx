import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UIMessageChunk } from "ai";

import { addStatus, finishRun, startRun } from "@/lib/run";
import { messageFrom, stubChunks, stubChunksWith } from "@/test/stream";

import { Answer } from "./answer";

/** The stub's stream with its answer text replaced. */
function withText(text: string): UIMessageChunk[] {
  return stubChunks()
    .filter((chunk) => chunk.type !== "text-delta")
    .flatMap((chunk): UIMessageChunk[] =>
      chunk.type === "text-start"
        ? [chunk, { type: "text-delta", id: chunk.id, delta: text }]
        : [chunk],
    );
}

describe("Answer", () => {
  it("renders the stub's answer with its marker, source and badge", async () => {
    render(<Answer message={await messageFrom(stubChunks())} />);
    const answer = screen.getByRole("article", { name: "Answer" });
    expect(answer).toHaveTextContent("This is a stub answer from the Plumbline seed");
    expect(screen.getByRole("button", { name: "Source 1: Stub Act, s. 1" })).toBeInTheDocument();
    const sources = screen.getByRole("list", { name: "Sources" });
    expect(within(sources).getByRole("listitem")).toHaveTextContent(
      "This section exists only to exercise the interface.",
    );
    expect(answer).toHaveTextContent("1 source verified");
    expect(answer).toHaveTextContent("stub · full tier · replayed");
  });

  it("moves focus from a marker to its source card", async () => {
    render(<Answer message={await messageFrom(stubChunks())} />);
    await userEvent.setup().click(screen.getByRole("button", { name: /^Source 1/ }));
    const card = within(screen.getByRole("list", { name: "Sources" })).getByRole("listitem");
    expect(card).toHaveFocus();
    expect(card).toHaveAttribute("data-selected");
  });

  it("renders model Markdown as text: no raw HTML, no outside links", async () => {
    const text =
      'Read **this** <img src="x" onerror="alert(1)"> and [this link](javascript:alert(1)) ' +
      "or [that one](https://example.org) [1].";
    const { container } = render(<Answer message={await messageFrom(withText(text))} />);
    expect(container.querySelector("strong")).toHaveTextContent("this");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(screen.getByRole("article")).toHaveTextContent("and this link or that one");
    expect(screen.getByRole("button", { name: /^Source 1/ })).toBeInTheDocument();
  });

  it("names the part a partial answer leaves out", async () => {
    const reason = "Rent rises at renewal follow a decree that isn't in the corpus yet.";
    render(
      <Answer
        message={await messageFrom(stubChunksWith({ status: "partial", abstain_reason: reason }))}
      />,
    );
    const answer = screen.getByRole("article", { name: "Answer" });
    expect(answer).toHaveTextContent("Partial answer");
    expect(answer).toHaveTextContent("This is a stub answer");
    expect(answer).toHaveTextContent(`Not covered by the statutes I hold${reason}`);
    expect(screen.getByRole("list", { name: "Sources" })).toBeInTheDocument();
  });

  it("shows an abstention calmly, with what was checked and no body or sources", async () => {
    const message = await messageFrom(
      stubChunksWith(
        {
          status: "abstained",
          jurisdictions: [],
          as_of: "2024-03-01",
          abstain_reason: "The stub has no corpus.",
        },
        { citations: false },
      ),
    );
    render(<Answer message={message} />);
    const abstention = screen.getByRole("region", {
      name: "I couldn't find a statute that answers this.",
    });
    expect(abstention).toHaveTextContent(
      "SearchedThe tenancy statutes of Dubai, Spain, Colombia and Florida",
    );
    expect(abstention).toHaveTextContent("Law as of1 Mar 2024");
    expect(abstention).toHaveTextContent("WhyThe stub has no corpus.");
    expect(screen.getByRole("article")).toHaveTextContent("Abstained");
    expect(screen.queryByText(/This is a stub answer/)).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Sources" })).not.toBeInTheDocument();
  });

  it("shows its status steps while it streams, and announces the active one", async () => {
    const run = addStatus(
      addStatus(startRun(0, 2), { stage: "detecting", detail: null }, 100),
      { stage: "retrieving", detail: null },
      300,
    );
    render(<Answer message={await messageFrom(stubChunks())} run={run} streaming />);
    const steps = screen.getByRole("list", { name: "What Plumbline is doing" });
    expect(steps).toHaveTextContent("Reading your question0.2 s");
    expect(steps).toHaveTextContent("Searching 2 jurisdictions");
    expect(screen.getByText("Searching 2 jurisdictions…")).toHaveClass("sr-only");
    expect(screen.queryByText(/Answered in/)).not.toBeInTheDocument();
  });

  it("collapses the steps into the meta line, one click away under Trace", async () => {
    const run = finishRun(
      addStatus(startRun(0, 4), { stage: "retrieving", detail: "40 passages" }, 200),
      4200,
    );
    render(<Answer message={await messageFrom(stubChunks())} run={run} />);
    expect(screen.getByRole("article")).toHaveTextContent("Answered in 4.2 s");
    const trace = screen.getByRole("button", { name: "Trace" });
    expect(trace).toHaveAttribute("aria-expanded", "false");
    await userEvent.setup().click(trace);
    expect(trace).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("list", { name: "What Plumbline is doing" })).toHaveTextContent(
      "Searching 4 jurisdictions · 40 passages4.0 s",
    );
  });
});
