"use client";

import { Toast } from "@base-ui/react/toast";
import { useMemo, type ReactNode } from "react";

import { CheckIcon } from "@/components/icons";

export type ToastAction = { label: string; onClick: () => void };

type ToastData = { icon?: "check" | "spinner" };

/** Confirmations leave after 4 seconds, paused while the pointer or focus is on them. */
const CONFIRM_MS = 4000;

/** Toast spec: one line on the inverse ground, bottom-right (bottom-centre on phones), with at
 * most one underlined action. A confirmation of something the reader did ("Reference copied")
 * leaves after 4 s; a long job stays until it ends. The provider also gives the viewport its
 * F6 landmark and the swipe to dismiss. */
export function ToastProvider({ children }: { children: ReactNode }) {
  return (
    <Toast.Provider limit={3} timeout={CONFIRM_MS}>
      {children}
      <Toast.Portal>
        <Toast.Viewport className="fixed inset-x-4 bottom-4 z-(--pl-z-toast) flex flex-col items-center gap-2 md:inset-x-auto md:right-6 md:bottom-6 md:items-end">
          <ToastList />
        </Toast.Viewport>
      </Toast.Portal>
    </Toast.Provider>
  );
}

function ToastList() {
  const { toasts } = Toast.useToastManager<ToastData>();
  return toasts.map((toast) => (
    <Toast.Root
      key={toast.id}
      toast={toast}
      className="flex w-full max-w-100 items-center gap-3 rounded-lg bg-inverse px-3.5 py-2.5 text-ui text-fg-inverse shadow-2 transition-[opacity,translate] duration-(--pl-duration-base) ease-enter data-ending-style:translate-y-2 data-ending-style:opacity-0 data-limited:hidden data-starting-style:translate-y-2 data-starting-style:opacity-0 md:w-auto md:min-w-70"
    >
      <Toast.Content className="flex flex-1 items-center gap-3">
        {toast.data?.icon === "check" && <CheckIcon className="shrink-0" />}
        {toast.data?.icon === "spinner" && (
          <span
            aria-hidden="true"
            className="size-3.5 shrink-0 animate-spin rounded-full border-2 border-fg-inverse/40 border-t-fg-inverse motion-reduce:animate-none"
          />
        )}
        <Toast.Title className="flex-1 text-ui" />
        <Toast.Action className="shrink-0 rounded-xs text-ui font-semibold underline underline-offset-2 focus-visible:outline-focus-inverse" />
      </Toast.Content>
    </Toast.Root>
  ));
}

export type ToastHandle = {
  /** Replaces the toast's text, icon or action, for a job that moves from running to done. */
  update: (next: { label: string; action?: ToastAction; done?: boolean }) => void;
  close: () => void;
};

/** Confirmations and jobs, from anywhere under the provider. */
export function useToasts() {
  const manager = Toast.useToastManager<ToastData>();
  return useMemo(() => {
    const action = (a?: ToastAction) => (a ? { children: a.label, onClick: a.onClick } : undefined);
    return {
      /** "Reference copied": a check and a line, gone after 4 s. */
      confirm(label: string, a?: ToastAction): void {
        manager.add({ title: label, data: { icon: "check" }, actionProps: action(a) });
      },
      /** "Checking lease · 8 of 14 clauses": a spinner that stays until it is updated or closed. */
      job(label: string, a?: ToastAction): ToastHandle {
        const id = manager.add({
          title: label,
          timeout: 0,
          data: { icon: "spinner" },
          actionProps: action(a),
        });
        return {
          update: (next) =>
            manager.update(id, {
              title: next.label,
              timeout: next.done ? CONFIRM_MS : 0,
              data: { icon: next.done ? "check" : "spinner" },
              actionProps: action(next.action),
            }),
          close: () => manager.close(id),
        };
      },
    };
  }, [manager]);
}
