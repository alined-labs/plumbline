import { APICallError } from "ai";

import { streamErrorText } from "./chat-engine";

describe("streamErrorText", () => {
  it("keeps the API's words when it stopped an answer in the stream", () => {
    expect(streamErrorText(new Error("Today's budget for live answers is used up."))).toBe(
      "Today's budget for live answers is used up.",
    );
  });

  it("has no words for a refusal before the stream or a failed connection", () => {
    const refused = new APICallError({
      message: "Internal Server Error",
      url: "http://localhost:8000/api/ask",
      requestBodyValues: {},
      statusCode: 500,
    });
    expect(streamErrorText(refused)).toBeNull();
    expect(streamErrorText(new TypeError("Failed to fetch"))).toBeNull();
    expect(streamErrorText(new Error("   "))).toBeNull();
    expect(streamErrorText("not an error")).toBeNull();
  });
});
