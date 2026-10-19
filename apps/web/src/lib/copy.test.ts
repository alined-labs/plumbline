// @vitest-environment node
import { readFileSync } from "node:fs";

import { DISCLAIMER } from "./copy";

const openapi = JSON.parse(
  readFileSync(new URL("../../../../packages/ts-client/openapi.json", import.meta.url), "utf8"),
) as {
  components: { schemas: { AnswerSummary: { properties: { disclaimer: { default: string } } } } };
};

describe("product copy", () => {
  it("shows the same disclaimer the API sends", () => {
    expect(DISCLAIMER).toBe(openapi.components.schemas.AnswerSummary.properties.disclaimer.default);
  });
});
