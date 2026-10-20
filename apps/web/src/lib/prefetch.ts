// What a first answer needs but a first paint does not: the Markdown renderer and the source
// panel. They are separate chunks, started when the reader focuses the question or asks, so
// they are there by the time an answer is (docs/notes/mobile-performance.md).

let started = false;

/** Starts loading the answer's chunks, once. Safe to call from any event handler. */
export function prefetchAnswerChunks(): void {
  if (started) return;
  started = true;
  void import("@/components/answer/answer-body");
  void import("@/components/answer/source-panel");
}
