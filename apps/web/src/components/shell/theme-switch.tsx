"use client";

import { Switch } from "@base-ui/react/switch";
import { useId, useSyncExternalStore } from "react";

import { MoonIcon } from "@/components/icons";
import { chooseTheme, chosenTheme, onThemeChange } from "@/lib/theme";
import { useMediaQuery } from "@/lib/use-media-query";

/** Sidebar spec, footer: "Dark theme" as a switch. It shows the theme in use, chosen or the
 * system's, and turning it sets an explicit choice. */
export function ThemeSwitch({ compact = false }: { compact?: boolean }) {
  const chosen = useSyncExternalStore(onThemeChange, chosenTheme, () => null);
  const systemDark = useMediaQuery("(prefers-color-scheme: dark)");
  const dark = chosen ? chosen === "dark" : systemDark;

  const id = useId();

  return (
    <div
      className={`flex min-h-8 items-center gap-2 px-2.5 text-small text-fg ${compact ? "max-lg:justify-center" : "max-md:min-h-11"}`}
    >
      <MoonIcon className={`shrink-0 text-fg-muted ${compact ? "max-lg:hidden" : ""}`} />
      <label htmlFor={id} className={`flex-1 cursor-pointer ${compact ? "max-lg:sr-only" : ""}`}>
        Dark theme
      </label>
      {/* The track is 18px high; the transparent ::before makes the target 26px (24px minimum). */}
      <Switch.Root
        id={id}
        nativeButton
        render={<button type="button" />}
        checked={dark}
        onCheckedChange={(checked) => chooseTheme(checked ? "dark" : "light")}
        className="relative flex h-4.5 w-8 shrink-0 items-center rounded-full bg-border-control p-0.5 transition-colors before:absolute before:inset-x-0 before:-inset-y-1 data-checked:bg-accent"
      >
        <Switch.Thumb className="size-3.5 rounded-full bg-surface shadow-1 transition-transform data-checked:translate-x-3.5" />
      </Switch.Root>
    </div>
  );
}
