import { useId, type ReactNode, type SelectHTMLAttributes } from "react";

import { ChevronDownIcon, CircleAlertIcon } from "@/components/icons";

// Field spec: a control is `control-md` high (`control-lg` and 16px text on phones, so the page
// does not zoom on focus) with a `border-control` edge, which holds 3:1 on every ground, so the
// control is visible without its label. Each class sets the properties it owns once.
export const controlClass =
  "h-(--pl-control-md) w-full rounded-md border border-border-control bg-surface px-3 text-ui text-fg " +
  "placeholder:text-fg-subtle hover:border-fg-subtle aria-invalid:border-danger " +
  "max-md:h-(--pl-control-lg) max-md:text-input";

type ControlProps = {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
};

/** Field spec: a visible label above the control, help below it, and an error that replaces
 * the help and says how to fix the input. The control gets its id, `aria-describedby` and
 * `aria-invalid` from here, so the error is read when the control is focused. */
export function Field({
  label,
  help,
  error,
  children,
}: {
  label: string;
  help?: string;
  error?: string;
  children: (control: ControlProps) => ReactNode;
}) {
  const id = useId();
  const messageId = `${id}-message`;
  const described = error || help ? messageId : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-ui font-medium">
        {label}
      </label>
      {children({
        id,
        "aria-describedby": described,
        "aria-invalid": error ? true : undefined,
      })}
      {error ? (
        <p id={messageId} className="flex items-center gap-1.5 text-small font-medium text-danger">
          <CircleAlertIcon className="shrink-0" />
          {error}
        </p>
      ) : (
        help && (
          <p id={messageId} className="text-small text-fg-muted">
            {help}
          </p>
        )
      )}
    </div>
  );
}

/** A native select with the chevron the Field spec draws; for four to twelve options. */
export function Select({
  className = "",
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className="relative inline-flex w-full">
      <select {...props} className={`${controlClass} appearance-none pr-8.5 ${className}`}>
        {children}
      </select>
      <ChevronDownIcon className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-fg-muted" />
    </span>
  );
}
