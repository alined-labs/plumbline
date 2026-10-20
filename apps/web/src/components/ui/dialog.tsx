"use client";

import { Dialog } from "@base-ui/react/dialog";
import { useRef, type ReactNode } from "react";

import { buttonClass } from "./button";

/** Dialog spec: an interruption for a decision that cannot wait, such as the notice before the
 * first lease upload. A title, one or two paragraphs (the second in `fg-muted`), and the safe
 * choice on the left as secondary with the main choice on the right as primary. Focus moves to
 * the first action and returns to the trigger; Escape and the scrim close it, because nothing
 * here is destructive; Tab cycles inside. Above 768px it is centred, below it is a bottom
 * sheet. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  children,
  cancelLabel = "Cancel",
  confirm,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** The paragraphs: the first in `fg`, the rest in `fg-muted`. */
  children: ReactNode;
  cancelLabel?: string;
  confirm: { label: string; icon?: ReactNode };
  onConfirm: () => void;
}) {
  const cancel = useRef<HTMLButtonElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-(--pl-z-overlay) bg-overlay transition-opacity duration-(--pl-duration-base) data-ending-style:opacity-0 data-starting-style:opacity-0" />
        <Dialog.Popup
          initialFocus={cancel}
          className="fixed z-(--pl-z-dialog) flex flex-col gap-3 bg-surface-raised p-6 shadow-3 transition-[opacity,translate] duration-(--pl-duration-base) ease-enter max-md:inset-x-0 max-md:bottom-0 max-md:rounded-t-xl max-md:data-ending-style:translate-y-full max-md:data-starting-style:translate-y-full md:left-1/2 md:top-1/2 md:w-115 md:max-w-[calc(100%-2rem)] md:-translate-x-1/2 md:-translate-y-1/2 md:rounded-xl md:data-ending-style:opacity-0 md:data-starting-style:opacity-0"
        >
          <Dialog.Title className="text-heading-2">{title}</Dialog.Title>
          <div className="flex flex-col gap-3 text-body [&>p+p]:text-fg-muted">{children}</div>
          <div className="mt-2 flex justify-end gap-2">
            <Dialog.Close ref={cancel} className={buttonClass({ variant: "secondary" })}>
              {cancelLabel}
            </Dialog.Close>
            <button
              type="button"
              onClick={onConfirm}
              className={buttonClass({ variant: "primary" })}
            >
              {confirm.icon}
              {confirm.label}
            </button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
