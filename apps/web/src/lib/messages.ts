import type { PlumblineDataParts } from "@plumbline/ts-client";
import type { DataUIPart, UIMessage } from "ai";

/** A chat message whose data parts carry Plumbline's typed payloads. */
export type PlumblineMessage = UIMessage<never, PlumblineDataParts>;

type Part = PlumblineMessage["parts"][number];
type AnyDataPart = DataUIPart<PlumblineDataParts>;

function isDataPart(part: Part): part is AnyDataPart {
  return part.type.startsWith("data-");
}

/** Every payload of one data-part kind in a message, in stream order. */
export function dataParts<K extends keyof PlumblineDataParts>(
  message: PlumblineMessage,
  name: K,
): PlumblineDataParts[K][] {
  const type = `data-${name}`;
  return message.parts
    .filter(isDataPart)
    .filter((part) => part.type === type)
    .map((part) => part.data as PlumblineDataParts[K]);
}

export function messageText(message: PlumblineMessage): string {
  return message.parts.map((part) => (part.type === "text" ? part.text : "")).join("");
}
