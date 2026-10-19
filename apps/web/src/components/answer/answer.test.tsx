import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UIMessageChunk } from "ai";

import { messageFrom, stubChunks } from "@/test/stream";

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
});
