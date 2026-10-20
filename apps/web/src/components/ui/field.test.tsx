import { render, screen } from "@testing-library/react";

import { controlClass, Field, Select } from "./field";

describe("Field", () => {
  it("labels the control and points it at its help", () => {
    render(
      <Field label="Date signed" help="Some rules depend on when the lease was signed.">
        {(control) => <input type="date" className={controlClass} {...control} />}
      </Field>,
    );
    const input = screen.getByLabelText("Date signed");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).toHaveAccessibleDescription("Some rules depend on when the lease was signed.");
  });

  it("replaces the help with an error that says how to fix the input", () => {
    render(
      <Field label="Lease file" help="PDF or DOCX, up to 20 MB." error="Upload a PDF or DOCX file.">
        {(control) => <input type="file" {...control} />}
      </Field>,
    );
    const input = screen.getByLabelText("Lease file");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Upload a PDF or DOCX file.");
    expect(screen.queryByText("PDF or DOCX, up to 20 MB.")).not.toBeInTheDocument();
  });

  it("gives each field its own ids", () => {
    render(
      <>
        <Field label="One">{(control) => <input {...control} />}</Field>
        <Field label="Two">{(control) => <input {...control} />}</Field>
      </>,
    );
    expect(screen.getByLabelText("One").id).not.toBe(screen.getByLabelText("Two").id);
  });

  it("draws a native select with its options", () => {
    render(
      <Field label="Jurisdiction">
        {(control) => (
          <Select {...control}>
            <option value="">Detect from the lease</option>
            <option value="spain">Spain (ES)</option>
          </Select>
        )}
      </Field>,
    );
    expect(screen.getByRole("combobox", { name: "Jurisdiction" })).toHaveDisplayValue(
      "Detect from the lease",
    );
  });
});
