// A reader for server-sent events (WHATWG HTML, "Parsing an event stream") over fetch. The
// browser's EventSource cannot be used for the lease job: it hides the status and body of a
// refused request, which is where the failure codes are, and a test cannot stand one in.

export type SseEvent = {
  /** "message" when the event names none. */
  event: string;
  /** The data lines joined with a newline. */
  data: string;
  /** The last `id:` the stream has sent so far, which is what Last-Event-ID resumes from. */
  lastEventId: string | undefined;
};

// A line ends in CRLF, LF or a lone CR.
const LINE_END = /\r\n|\r|\n/;

/** The stream's events, in order. An event cut off by the end of the stream is dropped, as the
 * standard says: only an event followed by its blank line is complete. Comments and the
 * `retry` field are ignored. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "";
  let data: string[] = [];
  let lastEventId: string | undefined;
  let first = true;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      if (first) {
        buffer = buffer.replace(/^﻿/, "");
        first = false;
      }
      for (;;) {
        const end = LINE_END.exec(buffer);
        // A CR at the very end may be the first half of a CRLF: wait for the next chunk.
        if (!end || (end[0] === "\r" && end.index === buffer.length - 1)) break;
        const line = buffer.slice(0, end.index);
        buffer = buffer.slice(end.index + end[0].length);
        if (line === "") {
          if (data.length > 0)
            yield { event: event || "message", data: data.join("\n"), lastEventId };
          event = "";
          data = [];
        } else if (!line.startsWith(":")) {
          const colon = line.indexOf(":");
          const field = colon < 0 ? line : line.slice(0, colon);
          const text = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
          if (field === "event") event = text;
          else if (field === "data") data.push(text);
          else if (field === "id" && !text.includes("\0")) lastEventId = text;
        }
      }
    }
  } finally {
    // A reader that stops early (the lease check was cancelled) lets the connection go.
    await reader.cancel().catch(() => undefined);
  }
}
