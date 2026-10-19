# @plumbline/ts-client

Generated from the API, never edited by hand (`make openapi`):

- `openapi.json`: the API's schema, including the answer stream's data-part payloads as components.
- `src/schema.d.ts`: TypeScript types for it (openapi-typescript).
- `fixtures/ask-stub.sse`: the exact bytes `/api/ask` streams for a fixed question from the stub pipeline, which the API's tests and the browser's end-to-end tests share.

`src/index.ts` re-exports the types the front end uses and a typed client for the JSON routes. Tests fail when any generated file is stale.
