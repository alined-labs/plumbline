// Test helpers: messages built from the exact bytes the API's stub streams, so a unit test
// breaks when the stream contract changes, like the end-to-end tests do.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import type { AnswerSummary } from "@plumbline/ts-client";
import { readUIMessageStream, type UIMessageChunk } from "ai";

import type { PlumblineMessage } from "@/lib/messages";

// Vitest runs from apps/web; under jsdom import.meta.url is not a file URL.
export const STUB_STREAM = readFileSync(
  join(process.cwd(), "../../packages/ts-client/fixtures/ask-stub.sse"),
  "utf8",
);

/** The stream's chunks, in order, without the closing [DONE]. */
export function stubChunks(): UIMessageChunk[] {
  return STUB_STREAM.split("\n\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("data: ") && line !== "data: [DONE]")
    .map((line) => JSON.parse(line.slice("data: ".length)) as UIMessageChunk);
}

/** The stub's chunks with the data-answer payload changed, for the partial and abstained
 * shapes, and optionally without its citations. */
export function stubChunksWith(
  answer: Partial<AnswerSummary>,
  { citations = true }: { citations?: boolean } = {},
): UIMessageChunk[] {
  return stubChunks()
    .filter((chunk) => citations || chunk.type !== "data-citation")
    .map((chunk) =>
      chunk.type === "data-answer"
        ? { ...chunk, data: { ...(chunk.data as AnswerSummary), ...answer } }
        : chunk,
    );
}

/** The assistant message a list of chunks adds up to, as useChat would hold it. */
export async function messageFrom(chunks: UIMessageChunk[]): Promise<PlumblineMessage> {
  const stream = new ReadableStream<UIMessageChunk>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
  let message: PlumblineMessage | undefined;
  for await (const state of readUIMessageStream<PlumblineMessage>({ stream })) message = state;
  if (!message) throw new Error("the stream produced no message");
  return message;
}
