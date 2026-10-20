# ADR-0006: Thin orchestration over the provider SDKs, with no LangChain in the core path

- Status: proposed
- Date: 2026-10-19

## Context

The core path is short: detect the jurisdictions, retrieve, rerank, abstain early or generate, verify the citations, decide the status, and stream the result. Every step has a requirement that the rest of the project depends on:

1. Every model call replays from `cache/`, keyed on the exact request sent to the provider, so every published number rebuilds at no cost.
2. The answer's text streams while the model writes structured output, and the complete object is then validated and every quote checked against its chunk.
3. Untrusted text (statutes, uploads, the reader's question) reaches a model only inside delimited blocks, and the prompt reads no clock.
4. Each stage is timed, costed and traced, and abstention is a result with a reason, not an exception.

The SDKs had also moved past what we remembered: anthropic 1.13 removed `temperature`, and Gemini and Claude take JSON schemas through different fields with different restrictions. An orchestration framework would sit between our code and these changes.

## Decision

1. Each provider is called through its own SDK behind one small `LLMClient` protocol (`generation/llm.py`): retries, timeouts, cost and the cache are ours, and the cache key is the exact payload.
2. The pipeline is one async generator over plain functions (`generation/pipeline.py`); the prompt, schema, verifier and abstention rules are modules a reviewer can read in one sitting.
3. Tracing wraps the pipeline from outside (`observability/tracing.py`), reading its events; DeepEval is used only as a metric harness around our judge.
4. LangChain, LlamaIndex and similar frameworks stay out of the core path. They may be used in throwaway experiments, never in code the API or the evaluation runs.

The whole core path, from the clients through tracing, is about 1,800 lines of our own code, each module with its own tests.

## Consequences

- We own retries, streaming, structured-output quirks and cost accounting for three providers. That is code to maintain, but each piece is tested, including against real SDK response objects and recorded calls.
- Record and replay are exact: a recording is keyed on what was sent, so a changed prompt is a new key and a stale recording fails loudly instead of answering silently.
- A provider change is a new `LLMClient` implementation, and an SDK change shows up in one file.
- Reviewers can read the prompt, the verifier and the abstention rules as written, with no framework defaults in between.

## Alternatives considered

- LangChain (LCEL chains, output parsers, callbacks for tracing): it hides the payload behind its own abstractions, which breaks exact replay keys, and adds a large, fast-moving dependency to the path every answer takes.
- LlamaIndex query engines: strong at retrieval, but retrieval here is SQL inside Postgres ([ADR-0001](0001-monorepo-and-postgres-only-hybrid-search.md)), and its response synthesizers would replace exactly the parts that need to be ours: the prompt, the verifier and abstention.
- DSPy: prompt optimization is attractive once the golden set is large, but compiled prompts are hard to review line by line, and the judge must stay fixed while it is being calibrated.
- LiteLLM as a universal client: one more layer between us and the SDK changes above, for about 400 lines of client code that we would still have to test.
