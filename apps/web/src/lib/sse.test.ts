import { readSse, type SseEvent } from "./sse";

const encoder = new TextEncoder();

function streamOf(...chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      }
      controller.close();
    },
  });
}

async function read(...chunks: (string | Uint8Array)[]): Promise<SseEvent[]> {
  const events: SseEvent[] = [];
  for await (const event of readSse(streamOf(...chunks))) events.push(event);
  return events;
}

describe("readSse", () => {
  it("reads events with their names and data", async () => {
    const events = await read(
      'event: stage\ndata: {"stage":"reading"}\n\nevent: done\ndata: {}\n\n',
    );
    expect(events).toEqual([
      { event: "stage", data: '{"stage":"reading"}', lastEventId: undefined },
      { event: "done", data: "{}", lastEventId: undefined },
    ]);
  });

  it("joins data lines with a newline and names an unnamed event message", async () => {
    expect(await read("data: one\ndata: two\n\n")).toEqual([
      { event: "message", data: "one\ntwo", lastEventId: undefined },
    ]);
  });

  it("carries the last event ID forward to the events after it", async () => {
    const events = await read("id: 1\ndata: a\n\ndata: b\n\nid: 2\ndata: c\n\n");
    expect(events.map((event) => event.lastEventId)).toEqual(["1", "1", "2"]);
  });

  it("reads an event split anywhere, even inside a CRLF", async () => {
    const events = await read("event: sta", "ge\r", "\ndata: x\r\n\r", "\n");
    expect(events).toEqual([{ event: "stage", data: "x", lastEventId: undefined }]);
  });

  it("reads a character split between two chunks", async () => {
    const bytes = encoder.encode("data: café €\n\n");
    const middle = bytes.indexOf(0xc3) + 1; // between the two bytes of "é"
    const events = await read(bytes.slice(0, middle), bytes.slice(middle));
    expect(events[0]?.data).toBe("café €");
  });

  it("ignores comments, retry and fields it does not know, and a byte order mark", async () => {
    const events = await read("﻿: keep-alive\nretry: 100\nfoo: bar\ndata: x\n\n");
    expect(events).toEqual([{ event: "message", data: "x", lastEventId: undefined }]);
  });

  it("removes one space after the colon, not more", async () => {
    expect((await read("data:  two\n\ndata:none\n\n")).map((event) => event.data)).toEqual([
      " two",
      "none",
    ]);
  });

  it("drops an event the stream ends in the middle of", async () => {
    const events = await read("data: whole\n\ndata: cut off\n");
    expect(events.map((event) => event.data)).toEqual(["whole"]);
  });

  it("lets go of the connection when the reader stops early", async () => {
    let cancelled = false;
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        controller.enqueue(encoder.encode("data: again\n\n"));
      },
      cancel() {
        cancelled = true;
      },
    });
    for await (const event of readSse(body)) {
      expect(event.data).toBe("again");
      break;
    }
    expect(cancelled).toBe(true);
  });
});
