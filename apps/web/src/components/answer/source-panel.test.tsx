import type { Citation } from "@plumbline/ts-client";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";

import { SourcePanel } from "./source-panel";

// A citation of a source the committed corpus manifest holds, so the panel can name its
// edition and link the official text.
const citation: Citation = {
  n: 2,
  chunk_id: "fl-83-49",
  ref: {
    jurisdiction: "florida",
    law: "fl-stat-83",
    article: "83.49",
    paragraph: "3(a)",
    edition: "2026",
  },
  label: "Fla. Stat. § 83.49(3)(a)",
  quote: "the landlord shall have 15 days to return the security deposit",
  gloss: null,
  language: "en",
  verified: true,
  page: null,
};

const subject = { messageId: "m1", n: citation.n, citations: [citation] };

describe("SourcePanel", () => {
  it("names the source, quotes the law and links the official text", async () => {
    render(<SourcePanel subject={subject} onClose={() => {}} opener={createRef()} slot={null} />);
    const panel = await screen.findByRole("dialog", { name: "Fla. Stat. § 83.49(3)(a)" });
    expect(panel).toHaveTextContent("Source 2");
    expect(panel).toHaveTextContent("Florida Statutes 2026, chapter 83");
    expect(screen.getByText(citation.quote).closest("blockquote")).toHaveAttribute("lang", "en");
    const original = screen.getByRole("link", { name: /Open original/ });
    expect(original.getAttribute("href")).toMatch(/^https:\/\/www\.leg\.state\.fl\.us\//);
    expect(original).toHaveAttribute("target", "_blank");
  });

  it("copies the reference with the edition and the link", async () => {
    const user = userEvent.setup();
    render(<SourcePanel subject={subject} onClose={() => {}} opener={createRef()} slot={null} />);
    await user.click(await screen.findByRole("button", { name: "Copy reference" }));
    const copied = await navigator.clipboard.readText();
    expect(copied).toMatch(
      /^Fla\. Stat\. § 83\.49\(3\)\(a\), Florida Statutes 2026.*\(edition 2026\)\nhttps:/,
    );
    expect(screen.getByRole("button", { name: "Reference copied" })).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    render(<SourcePanel subject={subject} onClose={onClose} opener={createRef()} slot={null} />);
    await screen.findByRole("dialog");
    await userEvent.setup().keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });
});
