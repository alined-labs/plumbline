import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UIMessageChunk } from "ai";
import type { ComponentProps } from "react";

import { addStatus, finishRun, startRun } from "@/lib/run";
import { messageFrom, stubChunks, stubChunksWith } from "@/test/stream";

import { Answer as AnswerView } from "./answer";
import { PanelProvider } from "./panel-context";

// The panel lives above the page, so every answer renders inside its provider.
function Answer(props: ComponentProps<typeof AnswerView>) {
  return (
    <PanelProvider>
      <AnswerView {...props} />
    </PanelProvider>
  );
}

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

  it("opens the source panel from a marker and returns focus to it", async () => {
    const user = userEvent.setup();
    render(<Answer message={await messageFrom(stubChunks())} />);
    const marker = screen.getByRole("button", { name: "Source 1: Stub Act, s. 1" });
    await user.click(marker);
    const panel = await screen.findByRole("dialog", { name: "Stub Act, s. 1" });
    expect(within(panel).getByRole("heading", { name: "Stub Act, s. 1" })).toHaveFocus();
    expect(panel).toHaveTextContent("This section exists only to exercise the interface.");
    expect(marker).toHaveAttribute("aria-expanded", "true");

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(marker).toHaveFocus();
    expect(marker).toHaveAttribute("aria-expanded", "false");
  });

  it("opens the same passage from its source card", async () => {
    const user = userEvent.setup();
    render(<Answer message={await messageFrom(stubChunks())} />);
    const card = within(screen.getByRole("list", { name: "Sources" })).getByRole("button");
    await user.click(card);
    expect(await screen.findByRole("dialog", { name: "Stub Act, s. 1" })).toBeInTheDocument();
    expect(card).toHaveAttribute("aria-expanded", "true");
    await user.click(screen.getByRole("button", { name: "Close source panel" }));
    await waitFor(() => expect(card).toHaveFocus());
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
    expect(screen.getByRole("button", { name: "Source 1: Stub Act, s. 1" })).toBeInTheDocument();
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

  it("opens the panel on its Trace tab from the meta line, and returns focus", async () => {
    const user = userEvent.setup();
    const run = finishRun(
      addStatus(startRun(0, 4), { stage: "retrieving", detail: "40 passages" }, 200),
      4200,
    );
    render(<Answer message={await messageFrom(stubChunks())} run={run} />);
    expect(screen.getByRole("article")).toHaveTextContent("Answered in 4.2 s");
    const trace = screen.getByRole("button", { name: "Trace" });
    await user.click(trace);

    const panel = await screen.findByRole("dialog", { name: "How this answer was produced" });
    expect(within(panel).getByRole("tab", { name: "Trace" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(within(panel).getByRole("list", { name: "What Plumbline is doing" })).toHaveTextContent(
      "Searching 4 jurisdictions · 40 passages4.0 s",
    );
    expect(within(panel).getByRole("list", { name: "Time per stage" })).toHaveTextContent(
      "Writing the answer",
    );
    expect(panel).toHaveTextContent("Replayed from a recording");
    // No source is open, so no marker is active (the page behind an open panel is hidden from
    // the accessibility tree, hence hidden: true).
    expect(
      screen.getByRole("button", { name: "Source 1: Stub Act, s. 1", hidden: true }),
    ).toHaveAttribute("aria-expanded", "false");

    await user.keyboard("{Escape}");
    await waitFor(() => expect(trace).toHaveFocus());
  });

  it("switches between the Sources and Trace tabs inside the panel", async () => {
    const user = userEvent.setup();
    render(<Answer message={await messageFrom(stubChunks())} />);
    await user.click(screen.getByRole("button", { name: "Trace" }));
    const panel = await screen.findByRole("dialog");
    await user.click(within(panel).getByRole("tab", { name: /Sources/ }));
    expect(
      await within(panel).findByRole("heading", { name: "Stub Act, s. 1" }),
    ).toBeInTheDocument();
    expect(within(panel).getByRole("tab", { name: /Sources/ })).toHaveTextContent("1");
    expect(panel).toHaveTextContent("This section exists only to exercise the interface.");
  });

  it("copies the finished answer with its sources and the disclaimer", async () => {
    const user = userEvent.setup();
    render(<Answer message={await messageFrom(stubChunks())} />);
    await user.click(screen.getByRole("button", { name: "Copy answer" }));
    const copied = await navigator.clipboard.readText();
    expect(copied).toContain("Plumbline seed [1].");
    expect(copied).toContain(
      '[1] Stub Act, s. 1: "This section exists only to exercise the interface."',
    );
    expect(copied).toContain("Legal information, not legal advice.");
    expect(screen.getByRole("button", { name: "Answer copied" })).toBeInTheDocument();
  });

  it("offers no actions while the answer streams", async () => {
    render(<Answer message={await messageFrom(stubChunks())} streaming />);
    expect(screen.queryByRole("button", { name: "Copy answer" })).not.toBeInTheDocument();
  });
});
