import { render, screen, within } from "@testing-library/react";

import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("offers one example per jurisdiction when all four are indexed", () => {
    render(<EmptyState onExample={vi.fn()} unindexed={[]} />);
    const examples = screen.getByRole("list", { name: "Example questions" });
    expect(within(examples).getAllByRole("button")).toHaveLength(4);
    expect(screen.queryByText(/join shortly/)).toBeNull();
  });

  it("offers no example for a jurisdiction not yet indexed, and says it joins shortly", () => {
    render(<EmptyState onExample={vi.fn()} unindexed={["dubai"]} />);
    const examples = screen.getByRole("list", { name: "Example questions" });
    expect(within(examples).getAllByRole("button")).toHaveLength(3);
    expect(within(examples).queryByText("AE-DU")).toBeNull();
    expect(
      screen.getByText(
        /Dubai's statutes join shortly; until then Plumbline declines questions on it\./,
      ),
    ).toBeInTheDocument();
  });

  it("names every jurisdiction still to come", () => {
    render(<EmptyState onExample={vi.fn()} unindexed={["dubai", "colombia"]} />);
    expect(
      screen.getByText(
        /Dubai and Colombia's statutes join shortly; until then Plumbline declines questions on them\./,
      ),
    ).toBeInTheDocument();
  });
});
