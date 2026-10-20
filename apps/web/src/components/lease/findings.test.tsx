import { render, screen, within } from "@testing-library/react";

import { finding } from "@/test/lease";

import { FindingCard } from "./finding-card";
import { Findings } from "./findings";

describe("FindingCard", () => {
  it("sets the clause beside the law, with the verdict, the reason and the confidence", () => {
    render(<FindingCard finding={finding()} />);
    const card = screen.getByRole("article");
    expect(within(card).getByRole("heading", { level: 4 })).toHaveTextContent(
      "The clause waives rights the law gives the tenant",
    );
    expect(card).toHaveTextContent("ConflictsThe clause waives rights");
    expect(card).toHaveTextContent("US-FL");
    expect(card).toHaveTextContent("Clause 12.3");
    expect(within(card).getByText(/The Tenant waives all rights/)).toHaveAttribute("lang", "en");
    expect(card).toHaveTextContent("The law · Fla. Stat. § 83.47(1)(a)");
    expect(within(card).getByText(/Purports to waive or preclude/).tagName).toBe("MARK");
    expect(card).toHaveTextContent("Florida law makes a clause void");
    expect(card).toHaveTextContent("Confidence 0.86");
  });

  it("quotes a Spanish statute in Spanish and glosses it in English", () => {
    const [citation] = finding().citations;
    if (!citation) throw new Error("the fixture has a citation");
    render(
      <FindingCard
        finding={finding({
          clause_language: "es",
          clause_text: "La fianza será de dos mensualidades.",
          citations: [
            {
              ...citation,
              language: "es",
              quote: "una mensualidad de renta",
              gloss: "one month's rent",
            },
          ],
        })}
      />,
    );
    expect(screen.getByText("La fianza será de dos mensualidades.")).toHaveAttribute("lang", "es");
    expect(screen.getByText("una mensualidad de renta").closest("p")).toHaveAttribute("lang", "es");
    expect(screen.getByText("one month's rent")).toBeInTheDocument();
  });

  it("shows only verified citations", () => {
    const [citation] = finding().citations;
    if (!citation) throw new Error("the fixture has a citation");
    render(
      <FindingCard
        finding={finding({
          citations: [
            citation,
            { ...citation, n: 2, label: "Fla. Stat. § 83.99", verified: false },
          ],
        })}
      />,
    );
    expect(screen.getByRole("article")).not.toHaveTextContent("83.99");
  });
});

describe("Findings", () => {
  it("groups the cards under counted headings, with a summary and no score", () => {
    render(
      <Findings
        findings={[
          finding({ n: 1, severity: "conflict" }),
          finding({ n: 2, severity: "check", title: "Depends on the rent index" }),
          finding({ n: 3, severity: "match", title: "The deposit follows the cap" }),
          finding({ n: 4, severity: "match", title: "The notice period follows the law" }),
        ]}
      />,
    );
    const summary = screen.getByLabelText("Summary of findings");
    expect(summary).toHaveTextContent("1 conflicts with the law");
    expect(summary).toHaveTextContent("1 worth checking");
    expect(summary).toHaveTextContent("2 match the law");
    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual([
      "Conflicts with the law1",
      "Worth checking1",
      "Matches the law2",
    ]);
    expect(screen.getAllByRole("article")).toHaveLength(4);
    expect(screen.queryByText(/score|grade/i)).not.toBeInTheDocument();
  });
});
