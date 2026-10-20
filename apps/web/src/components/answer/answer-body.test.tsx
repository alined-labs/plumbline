import type { Citation } from "@plumbline/ts-client";
import { render, screen } from "@testing-library/react";

import { AnswerBody } from "./answer-body";

const citation: Citation = {
  n: 1,
  chunk_id: "c-1",
  ref: { jurisdiction: "spain", law: "es-lau", article: "36", paragraph: null, edition: "2025" },
  label: "Ley 29/1994, art. 36",
  quote: "La fianza será de una mensualidad.",
  gloss: "The deposit is one month's rent.",
  language: "es",
  verified: true,
  page: null,
};

describe("AnswerBody", () => {
  it("renders the same elements when it renders block by block", () => {
    const { container } = render(
      <AnswerBody
        markdown={"The deposit is one month [1](#source-1).\n\nIt is returned.\n\n- One\n- Two"}
        citations={[citation]}
        active={null}
        onOpen={() => {}}
      />,
    );
    const body = container.firstElementChild;
    expect([...(body?.children ?? [])].map((element) => element.tagName)).toEqual(["P", "P", "UL"]);
    expect(body?.querySelectorAll("li")).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: "Source 1: Ley 29/1994, art. 36" }),
    ).toBeInTheDocument();
  });
});
