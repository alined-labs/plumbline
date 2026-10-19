// The Button spec as classes, so a <button>, a Base UI part or a Next <Link> can share them.
// Each variant sets its own edge and each size its own type, gap and padding, so two utilities
// for one property never meet (Tailwind orders them by its stylesheet, not by the class
// string). Below 768px every button grows to the 44px touch target.
const base =
  "inline-flex shrink-0 items-center whitespace-nowrap rounded-md border " +
  "font-medium transition-colors " +
  "disabled:cursor-not-allowed disabled:opacity-45 aria-disabled:cursor-not-allowed aria-disabled:opacity-45 " +
  "max-md:h-(--pl-control-lg) max-md:min-w-(--pl-control-lg)";

const variants = {
  primary:
    "border-transparent bg-accent text-accent-fg hover:bg-accent-hover active:bg-accent-active",
  secondary: "border-border-strong bg-surface text-fg hover:bg-bg-hover active:bg-bg-active",
  ghost: "border-transparent text-fg hover:bg-bg-hover active:bg-bg-active",
  danger: "border-transparent bg-danger text-on-status hover:bg-danger-hover",
} as const;

const sizes = {
  sm: {
    box: "h-(--pl-control-sm) gap-1.5 text-small",
    pad: "px-2.5",
    square: "w-(--pl-control-sm)",
  },
  md: { box: "h-(--pl-control-md) gap-2 text-ui", pad: "px-3.5", square: "w-(--pl-control-md)" },
  lg: { box: "h-(--pl-control-lg) gap-2 text-body", pad: "px-4.5", square: "w-(--pl-control-lg)" },
} as const;

export type ButtonVariant = keyof typeof variants;
export type ButtonSize = keyof typeof sizes;

export function buttonClass({
  variant = "secondary",
  size = "md",
  icon = false,
  start = false,
  className = "",
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Icon-only: square, no side padding. It still needs an aria-label. */
  icon?: boolean;
  /** Content from the leading edge, for full-width buttons in lists. */
  start?: boolean;
  className?: string;
} = {}): string {
  const { box, pad, square } = sizes[size];
  return [
    base,
    variants[variant],
    box,
    icon ? square : pad,
    start ? "justify-start" : "justify-center",
    className,
  ]
    .filter(Boolean)
    .join(" ");
}
