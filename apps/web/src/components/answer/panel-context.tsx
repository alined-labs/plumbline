"use client";

import dynamic from "next/dynamic";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { PanelSubject } from "./source-panel";

export type { PanelSubject };

// The panel (a Dialog, Tabs and their positioning code) is the largest piece of the shell and
// no page needs it until a source or a trace is opened, so it loads then, as its own chunk.
const SourcePanel = dynamic(() => import("./source-panel").then((module) => module.SourcePanel), {
  ssr: false,
});

type PanelApi = {
  subject: PanelSubject | null;
  /** Opens (or switches) the panel; focus returns to `opener` when it closes. */
  open: (subject: PanelSubject, opener: HTMLElement) => void;
  /** Switches the source or the tab of the open panel. */
  update: (patch: Partial<Pick<PanelSubject, "n" | "tab">>) => void;
  close: () => void;
};

const PanelContext = createContext<PanelApi | null>(null);
const SlotContext = createContext<(element: HTMLElement | null) => void>(() => {});

export function usePanel(): PanelApi {
  const panel = useContext(PanelContext);
  if (!panel) throw new Error("usePanel needs a PanelProvider above it");
  return panel;
}

/** The source panel's state, kept above the page so the AppShell's panes can follow it: the
 * panel is a third pane beside the conversation from 1024px, and `data-panel` on <html> lets
 * the sidebar fold to its rail while it is open. The panel itself renders here. */
export function PanelProvider({ children }: { children: ReactNode }) {
  const [subject, setSubject] = useState<PanelSubject | null>(null);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const opener = useRef<HTMLElement | null>(null);

  const open = useCallback((next: PanelSubject, from: HTMLElement) => {
    opener.current = from;
    setSubject(next);
  }, []);
  const update = useCallback(
    (patch: Partial<Pick<PanelSubject, "n" | "tab">>) =>
      setSubject((current) => (current ? { ...current, ...patch } : current)),
    [],
  );
  const close = useCallback(() => setSubject(null), []);
  const api = useMemo(() => ({ subject, open, update, close }), [subject, open, update, close]);

  const isOpen = subject !== null;
  useEffect(() => {
    document.documentElement.dataset.panel = isOpen ? "open" : "closed";
    return () => {
      delete document.documentElement.dataset.panel;
    };
  }, [isOpen]);

  // Rendered from the first open on, and kept after, so the closing animation can finish.
  const [mounted, setMounted] = useState(false);
  if (subject && !mounted) setMounted(true);

  return (
    <PanelContext value={api}>
      <SlotContext value={setSlot}>
        {children}
        {mounted && (
          <SourcePanel
            subject={subject}
            onChange={update}
            onClose={close}
            opener={opener}
            slot={slot}
          />
        )}
      </SlotContext>
    </PanelContext>
  );
}

/** The AppShell's third pane: empty while the panel is closed, so it takes no width. From
 * 1024px the open panel renders into it, beside the conversation. */
export function PanelSlot() {
  const setSlot = useContext(SlotContext);
  return <div ref={setSlot} className="sticky top-0 hidden h-dvh shrink-0 lg:block" />;
}
