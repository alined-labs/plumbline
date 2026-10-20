"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType } from "react";

import { Logo, LogoMark } from "@/components/brand/logo";
import {
  BookOpenIcon,
  FileCheckIcon,
  GaugeIcon,
  MessageSquareIcon,
  PlusIcon,
  type IconProps,
} from "@/components/icons";
import { buttonClass } from "@/components/ui/button";
import { Tip } from "@/components/ui/tip";
import { useMediaQuery } from "@/lib/use-media-query";

import { ThemeSwitch } from "./theme-switch";

export const DESTINATIONS: { href: Route; label: string; Icon: ComponentType<IconProps> }[] = [
  { href: "/", label: "Ask", Icon: MessageSquareIcon },
  { href: "/check-lease", label: "Check a lease", Icon: FileCheckIcon },
  { href: "/evals", label: "Evaluation", Icon: GaugeIcon },
  { href: "/about", label: "About", Icon: BookOpenIcon },
];

/** The export uses trailing slashes ("/evals/"); destinations are written without them. */
function isCurrent(pathname: string, href: string): boolean {
  const path = pathname.replace(/(.)\/+$/, "$1");
  return href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
}

/**
 * The sidebar's contents (Sidebar spec). `aside` is the column beside the page: full width
 * from 1024px, the 56px rail with names in tooltips from 768px. `drawer` is the same list
 * inside the phone drawer, always with its names.
 */
export function SidebarContent({
  mode,
  onNavigate,
}: {
  mode: "aside" | "drawer";
  onNavigate?: () => void;
}) {
  const pathname = usePathname() ?? "/";
  // The rail hides the names, so only there do the tooltips carry them.
  const wide = useMediaQuery("(min-width: 1024px)", true);
  const rail = mode === "aside" && !wide;
  // In the aside, the names hide by CSS below 1024px so the static HTML is right before
  // hydration; they stay in the accessibility tree either way.
  const nameClass = mode === "aside" ? "max-lg:sr-only" : "";
  const target = mode === "drawer" ? "min-h-11" : "h-8.5";
  const centred = mode === "aside" ? "max-lg:justify-center max-lg:px-0" : "";

  return (
    <nav aria-label="Plumbline" className="flex flex-1 flex-col gap-0.5">
      <Link
        href="/"
        aria-label="Plumbline home"
        onClick={onNavigate}
        className={`mb-2 flex items-center rounded-sm px-2 text-fg ${target} ${centred}`}
      >
        {mode === "aside" && <LogoMark className="size-6 lg:hidden" />}
        <Logo className={`h-5.5 w-auto ${mode === "aside" ? "max-lg:hidden" : ""}`} />
      </Link>
      <Tip label="New question" side="right" enabled={rail}>
        <Link
          href="/"
          onClick={onNavigate}
          className={buttonClass({ start: true, className: `mb-2 w-full ${centred}` })}
        >
          <PlusIcon />
          <span className={nameClass}>New question</span>
        </Link>
      </Tip>
      {DESTINATIONS.map(({ href, label, Icon }) => (
        <Tip key={href} label={label} side="right" enabled={rail}>
          <Link
            href={href}
            onClick={onNavigate}
            aria-current={isCurrent(pathname, href) ? "page" : undefined}
            className={`flex items-center gap-2.5 rounded-md px-2.5 text-ui text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg aria-[current=page]:bg-bg-active aria-[current=page]:text-fg ${target} ${centred}`}
          >
            <Icon />
            <span className={nameClass}>{label}</span>
          </Link>
        </Tip>
      ))}
      <div className="mt-auto pt-3">
        <ThemeSwitch compact={mode === "aside"} />
      </div>
    </nav>
  );
}
