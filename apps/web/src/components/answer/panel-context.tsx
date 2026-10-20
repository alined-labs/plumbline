"use client";

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

import { SourcePanel, type PanelSubject } from "./source-panel";

export type { PanelSubject };

type PanelApi = {
  subject: PanelSubject | null;
  /** Opens (or switches) the panel; focus returns to `opener` when it closes. */
  open: (subject: PanelSubject, opener: HTMLElement) => void;
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
  const close = useCallback(() => setSubject(null), []);
  const api = useMemo(() => ({ subject, open, close }), [subject, open, close]);

  const isOpen = subject !== null;
  useEffect(() => {
    document.documentElement.dataset.panel = isOpen ? "open" : "closed";
    return () => {
      delete document.documentElement.dataset.panel;
    };
  }, [isOpen]);

  return (
    <PanelContext value={api}>
      <SlotContext value={setSlot}>
        {children}
        <SourcePanel subject={subject} onClose={close} opener={opener} slot={slot} />
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
