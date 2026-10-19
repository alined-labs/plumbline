"use client";

import { Dialog } from "@base-ui/react/dialog";
import Link from "next/link";
import { useState } from "react";

import { Logo } from "@/components/brand/logo";
import { MenuIcon, XIcon } from "@/components/icons";
import { buttonClass } from "@/components/ui/button";

import { SidebarContent } from "./sidebar";

/** Below 768px: the top bar with the menu button, and the sidebar as a focus-trapped drawer
 * that Escape, the scrim, the close button or a destination closes. */
export function MobileBar() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <div className="sticky top-0 z-(--pl-z-sticky) flex h-(--pl-topbar-height) items-center gap-2 border-b border-border bg-bg px-2 md:hidden">
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Trigger
          aria-label="Open navigation"
          className={buttonClass({ variant: "ghost", icon: true })}
        >
          <MenuIcon />
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Backdrop className="fixed inset-0 z-(--pl-z-overlay) bg-overlay transition-opacity duration-(--pl-duration-base) data-ending-style:opacity-0 data-starting-style:opacity-0" />
          <Dialog.Popup className="fixed inset-y-0 left-0 z-(--pl-z-dialog) flex w-(--pl-sidebar-width) flex-col gap-2 border-r border-border bg-bg-subtle px-2.5 py-3 shadow-3 transition-transform duration-(--pl-duration-slow) ease-enter data-ending-style:-translate-x-full data-starting-style:-translate-x-full">
            <div className="flex items-center justify-between">
              <Dialog.Title className="px-2 text-eyebrow font-mono uppercase text-fg-muted">
                Menu
              </Dialog.Title>
              <Dialog.Close
                aria-label="Close navigation"
                className={buttonClass({ variant: "ghost", icon: true })}
              >
                <XIcon />
              </Dialog.Close>
            </div>
            <SidebarContent mode="drawer" onNavigate={close} />
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>
      <Link
        href="/"
        aria-label="Plumbline home"
        className="flex min-h-11 items-center rounded-sm px-1 text-fg"
      >
        <Logo className="h-5.5 w-auto" />
      </Link>
    </div>
  );
}
