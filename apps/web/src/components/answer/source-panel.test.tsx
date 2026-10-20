import type { Citation } from "@plumbline/ts-client";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";

import { ARTICLE, mockArticle } from "@/test/article";
import { QueryWrapper } from "@/test/query";

import { SourcePanel, type PanelSubject } from "./source-panel";

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

const subject: PanelSubject = {
  messageId: "m1",
  citations: [citation],
  n: citation.n,
  tab: "sources",
  trace: undefined,
  run: undefined,
};

/** The panel over the answer's one source, with the API's answer for its article. */
function renderPanel(onClose: () => void = () => {}) {
  return render(
    <SourcePanel
      subject={subject}
      onChange={() => {}}
      onClose={onClose}
      opener={createRef()}
      slot={null}
    />,
    { wrapper: QueryWrapper },
  );
}

afterEach(() => vi.restoreAllMocks());

describe("SourcePanel", () => {
  beforeEach(() => {
    mockArticle("pending");
  });

  it("names the source, quotes the law and links the official text", async () => {
    renderPanel();
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
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Copy reference" }));
    const copied = await navigator.clipboard.readText();
    expect(copied).toMatch(
      /^Fla\. Stat\. § 83\.49\(3\)\(a\), Florida Statutes 2026.*\(edition 2026\)\nhttps:/,
    );
    expect(screen.getByRole("button", { name: "Reference copied" })).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    renderPanel(onClose);
    await screen.findByRole("dialog");
    await userEvent.setup().keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("says the article is loading, and shows the quoted passage meanwhile", async () => {
    renderPanel();
    expect(await screen.findByText("Loading the whole article…")).toBeInTheDocument();
    expect(screen.getByText(citation.quote)).toBeInTheDocument();
  });
});

describe("SourcePanel with the article", () => {
  it("asks the API for the cited chunk, with the quote to place in it", async () => {
    const get = mockArticle(ARTICLE);
    renderPanel();
    await screen.findByRole("region", { name: "Article text" });
    expect(get).toHaveBeenCalledWith(
      "/api/chunks/{chunk_id}",
      expect.objectContaining({
        params: { path: { chunk_id: "fl-83-49" }, query: { quote: citation.quote } },
      }),
    );
  });

  it("shows the whole article with the cited words marked and where they sit", async () => {
    mockArticle(ARTICLE);
    renderPanel();
    const region = await screen.findByRole("region", { name: "Article text" });
    expect(region).toHaveTextContent("(3)(a) Upon the vacating of the premises");
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region.querySelector("mark")).toHaveTextContent(citation.quote);
    expect(region.querySelector("blockquote")).toHaveAttribute("lang", "en");
    expect(screen.getByText("Characters 147 to 208 of 254")).toBeInTheDocument();
    // The article's heading joins the statute's name in the header; its dates follow.
    const panel = screen.getByRole("dialog");
    expect(panel).toHaveTextContent("Deposit money or advance rent; duty of landlord and tenant");
    expect(screen.getByText("In force from 1 Jul 2013.")).toBeInTheDocument();
    expect(screen.queryByText("Loading the whole article…")).not.toBeInTheDocument();
  });

  it("says a provision is repealed before its text, in the publisher's own words", async () => {
    mockArticle({
      ...ARTICLE,
      article: {
        ...ARTICLE.article,
        status: "repealed",
        language: "es",
        validity_note:
          "Artículo derogado por el literal c) del artículo 626 de la Ley 1564 de 2012.",
      },
    });
    renderPanel();
    expect(await screen.findByText("This provision is repealed.")).toBeInTheDocument();
    expect(screen.getByText(/^Artículo derogado/)).toHaveAttribute("lang", "es");
  });

  it("keeps the quoted passage and says so when the article cannot be had", async () => {
    mockArticle("refused");
    renderPanel();
    expect(await screen.findByText(/full text isn't available right now/)).toBeInTheDocument();
    expect(screen.getByText(citation.quote)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Article text" })).not.toBeInTheDocument();
  });

  it("shows a restricted source as the quote alone, says why and links the original", async () => {
    const quote = Array.from(ARTICLE.article.text)
      .slice(ARTICLE.span?.start, ARTICLE.span?.end)
      .join("");
    mockArticle({
      ...ARTICLE,
      restricted: true,
      article: { ...ARTICLE.article, text: quote, heading: null, validity_note: null },
      span: { start: 0, end: Array.from(quote).length },
    });
    renderPanel();
    expect(await screen.findByText("Only the quoted passage.")).toBeInTheDocument();
    expect(screen.getByText(/publisher's terms do not let us show more/)).toBeInTheDocument();
    expect(screen.getByText(citation.quote).tagName).toBe("BLOCKQUOTE");
    expect(screen.queryByRole("region", { name: "Article text" })).not.toBeInTheDocument();
    expect(screen.queryByText(/^Characters /)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open original/ })).toHaveAttribute("href");
  });

  it("links the original from the API when the manifest lacks the source", async () => {
    mockArticle({
      ...ARTICLE,
      restricted: true,
      source: {
        id: "dubai-law-26-2007",
        title: "Law No. 26 of 2007",
        url: "https://dlp.dubai.gov.ae/",
      },
    });
    render(
      <SourcePanel
        subject={{
          ...subject,
          citations: [{ ...citation, ref: { ...citation.ref, law: "dubai-law-26-2007" } }],
        }}
        onChange={() => {}}
        onClose={() => {}}
        opener={createRef()}
        slot={null}
      />,
      { wrapper: QueryWrapper },
    );
    expect(await screen.findByRole("link", { name: /Open original/ })).toHaveAttribute(
      "href",
      "https://dlp.dubai.gov.ae/",
    );
  });

  it("falls back to the quote when it is not found in the article", async () => {
    mockArticle({ ...ARTICLE, span: null });
    renderPanel();
    await screen.findByRole("dialog");
    await waitFor(() =>
      expect(screen.queryByText("Loading the whole article…")).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("region", { name: "Article text" })).not.toBeInTheDocument();
    expect(screen.getByText(citation.quote)).toBeInTheDocument();
  });
});
