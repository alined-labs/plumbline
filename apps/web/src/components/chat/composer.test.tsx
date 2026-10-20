import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Composer } from "./composer";

function setup(busy = false) {
  const onAsk = vi.fn();
  const onStop = vi.fn();
  const user = userEvent.setup();
  render(<Composer busy={busy} onAsk={onAsk} onStop={onStop} />);
  return { onAsk, onStop, user, question: screen.getByLabelText("Your question") };
}

describe("Composer", () => {
  it("sends on Enter, keeps Shift+Enter for a new line, then clears the question", async () => {
    const { onAsk, user, question } = setup();
    expect(screen.getByRole("button", { name: "Send question" })).toBeDisabled();
    await user.type(question, "How long?{Shift>}{Enter}{/Shift}Miami{Enter}");
    await waitFor(() =>
      expect(onAsk).toHaveBeenCalledWith({
        question: "How long?\nMiami",
        jurisdictions: [],
        asOf: "",
      }),
    );
    await waitFor(() => expect(question).toHaveValue(""));
  });

  it("sends the jurisdictions chosen in the filter and the as-of date", async () => {
    const { onAsk, user, question } = setup();
    await user.click(screen.getByRole("combobox", { name: "Jurisdictions" }));
    await user.click(await screen.findByRole("option", { name: /Florida/ }));
    await user.keyboard("{Escape}");
    expect(screen.getByRole("combobox", { name: "Jurisdictions" })).toHaveTextContent(
      "FloridaUS-FL",
    );
    fireEvent.change(screen.getByLabelText("Law as of"), { target: { value: "2024-03-01" } });
    await user.type(question, "Deposit?{Enter}");
    await waitFor(() =>
      expect(onAsk).toHaveBeenCalledWith({
        question: "Deposit?",
        jurisdictions: ["florida"],
        asOf: "2024-03-01",
      }),
    );
  });

  it("offers Stop while an answer streams, and Escape stops it", async () => {
    const { onStop, user, question } = setup(true);
    await user.click(question);
    await user.keyboard("{Escape}");
    expect(onStop).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: /Stop/ }));
    expect(onStop).toHaveBeenCalledTimes(2);
  });

  it("focuses the question on / from anywhere but another field", async () => {
    const { user, question } = setup();
    await user.keyboard("/");
    expect(question).toHaveFocus();
    expect(question).toHaveValue("");
    await user.click(screen.getByLabelText("Law as of"));
    await user.keyboard("/");
    expect(question).not.toHaveFocus();
  });
});
