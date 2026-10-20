import { Profiler, type ProfilerOnRenderCallback, type ReactNode } from "react";

export type Commit = { phase: string; actual: number; base: number; at: number };

declare global {
  interface Window {
    /** React's commits of the chat, for e2e/profile-stream.mjs. */
    __plumblineCommits?: Commit[];
  }
}

const record: ProfilerOnRenderCallback = (_id, phase, actual, base, at) => {
  (window.__plumblineCommits ??= []).push({ phase, actual, base, at });
};

/** React's Profiler around the chat. It runs only in an export built for profiling
 * (NEXT_PUBLIC_PROFILE=1 next build --profile); in every other build the condition is a
 * constant and the wrapper disappears. See docs/notes/streamed-answer-profile.md. */
export function ChatProfiler({ children }: { children: ReactNode }) {
  return process.env.NEXT_PUBLIC_PROFILE === "1" ? (
    <Profiler id="chat" onRender={record}>
      {children}
    </Profiler>
  ) : (
    children
  );
}
