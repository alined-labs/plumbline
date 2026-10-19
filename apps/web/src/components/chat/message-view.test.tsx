import { render, screen } from "@testing-library/react";

import type { PlumblineMessage } from "@/lib/messages";

import { MessageView } from "./message-view";

const citation = {
  n: 1,
  chunk_id: "stub-act-1",
  ref: { jurisdiction: "florida", law: "stub-act", article: "1", edition: "seed", paragraph: null },
  label: "Stub Act, s. 1",
  quote: "This section exists only to exercise the interface.",
  gloss: null,
  language: "en",
  verified: true,
  page: null,
} as const;

function answer(status: "answered" | "abstained", withCitation: boolean): PlumblineMessage {
  return {
    id: "m1",
    role: "assistant",
    parts: [
      { type: "text", text: "A stub answer [1]." },
      ...(withCitation
        ? [{ type: "data-citation" as const, id: "citation-1", data: citation }]
        : []),
      {
        type: "data-answer",
        id: "answer",
        data: {
          status,
          jurisdictions: ["florida"],
          as_of: null,
          confidence: null,
          abstain_reason: status === "abstained" ? "No corpus yet" : null,
          invalid_citations: 0,
          disclaimer: "Legal information, not legal advice.",
        },
      },
    ],
  };
}

describe("MessageView", () => {
  it("shows the answer and its citations", () => {
    render(<MessageView message={answer("answered", true)} />);
    expect(screen.getByText("A stub answer [1].")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Citations" });
    expect(list).toHaveTextContent("Stub Act, s. 1");
    expect(list).toHaveTextContent("This section exists only to exercise the interface.");
  });

  it("says when Plumbline declined to answer", () => {
    render(<MessageView message={answer("abstained", false)} />);
    expect(screen.getByText(/declined to answer: No corpus yet/)).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Citations" })).not.toBeInTheDocument();
  });
});
