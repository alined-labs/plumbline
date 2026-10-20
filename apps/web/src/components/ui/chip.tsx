import type { ComponentProps } from "react";

/** Chip spec: a pill that toggles. Pressed, it takes the accent-subtle ground and a medium
 * weight, so the state is a style and `aria-pressed` for assistive technology both. 44 px
 * tall on phones. */
export function Chip({
  pressed,
  className = "",
  ...props
}: { pressed: boolean } & Omit<ComponentProps<"button">, "aria-pressed">) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      className={`inline-flex h-8 items-center gap-1.5 rounded-full border border-border-strong bg-surface px-3 text-ui hover:bg-bg-hover aria-pressed:border-accent-border aria-pressed:bg-accent-subtle aria-pressed:font-medium aria-pressed:text-accent-text max-md:h-11 ${className}`}
      {...props}
    />
  );
}
