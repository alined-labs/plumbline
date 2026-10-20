import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { api } from "@/lib/api";

import { FeedbackButtons, FeedbackPanel, useFeedback } from "./feedback";

function Harness() {
  const feedback = useFeedback("req_1");
  return (
    <>
      <div>
        <FeedbackButtons feedback={feedback} panelId="panel" />
      </div>
      <FeedbackPanel feedback={feedback} id="panel" />
    </>
  );
}

function setup(outcome: "ok" | "refused" = "ok") {
  const post = vi.spyOn(api, "POST").mockImplementation((async () => ({
    response: new Response(null, { status: outcome === "ok" ? 204 : 500 }),
  })) as unknown as typeof api.POST);
  render(<Harness />);
  return { post, user: userEvent.setup() };
}

afterEach(() => vi.restoreAllMocks());

describe("Feedback", () => {
  it("sends a thumbs up at once and thanks the reader", async () => {
    const { post, user } = setup();
    await user.click(screen.getByRole("button", { name: "Helpful" }));
    expect(post).toHaveBeenCalledWith("/api/feedback", {
      body: { request_id: "req_1", helpful: true },
    });
    expect(await screen.findByText("Thanks, that helps.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Helpful" })).toHaveAttribute("aria-pressed", "true");
  });

  it("opens the five reasons in the spec's order on Not helpful, puts focus on the first, and closes on Cancel", async () => {
    const { post, user } = setup();
    await user.click(screen.getByRole("button", { name: "Not helpful" }));
    const group = screen.getByRole("group", { name: "What went wrong?" });
    const chips = screen
      .getAllByRole("button", { pressed: false })
      .filter((b) => group.contains(b));
    expect(chips.map((chip) => chip.textContent)).toEqual([
      "Wrong citation",
      "Missed a statute",
      "Outdated law",
      "Hard to follow",
      "Something else",
    ]);
    expect(chips[0]).toHaveFocus();
    expect(screen.getByRole("button", { name: "Not helpful" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("sends the chosen reasons and the note, then collapses to a thank-you", async () => {
    const { post, user } = setup();
    await user.click(screen.getByRole("button", { name: "Not helpful" }));
    await user.click(screen.getByRole("button", { name: "Outdated law" }));
    await user.click(screen.getByRole("button", { name: "Wrong citation" }));
    await user.type(screen.getByLabelText("Note"), "The 2019 text is cited.");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(post).toHaveBeenCalledWith("/api/feedback", {
      body: {
        request_id: "req_1",
        helpful: false,
        reasons: ["wrong_citation", "outdated_law"],
        note: "The 2019 text is cited.",
      },
    });
    expect(await screen.findByText("Thanks, that helps.")).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("keeps the panel and says so when the feedback does not go through", async () => {
    const { user } = setup("refused");
    await user.click(screen.getByRole("button", { name: "Not helpful" }));
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Feedback didn't send.")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "What went wrong?" })).toBeInTheDocument();
    expect(screen.queryByText("Thanks, that helps.")).not.toBeInTheDocument();
  });
});
