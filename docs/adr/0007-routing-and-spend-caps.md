# ADR-0007: Route each request by a rule, under the demo tier and daily spend caps

- Status: proposed
- Date: 2026-10-19

## Context

Every question costs a model call, the budget is a US$100 credit, and the demo must stay up for months ([ADR-0002](0002-home-server-behind-a-tunnel-with-a-static-tier.md)). Most questions are single-article lookups that a small model answers well from good sources. Some compare jurisdictions or chain two questions, and those are harder. A lease check sends an upload, which is personal data.

What we read and measured on 2026-10-19 (prices per million tokens, paid tier):

1. Gemini 3.5 Flash-Lite costs $0.30 in and $2.50 out. Gemini 3.8 Flash costs $0.75 and $3.75, doubling on 2027-01-01, and thinks by default: one answer took 296 output tokens plus 661 thinking tokens. Claude Sonnet 5.5 costs $2 and $10; Claude Haiku 5.5 costs $0.10 and $0.50.
2. A recorded fast-route answer cost $0.0007 (810 tokens in, 182 out): about 1,400 answers per dollar. The same prompt on 3.8 Flash cost about $0.0044.
3. Google uses free-tier inputs to improve its products. On the paid tier it does not, for both Gemini models above, except on the invite-only Contributor tier, which we do not use. A key's tier is a property of its Cloud project, which code cannot check.

## Decision

1. Four routes, chosen by a rule in `generation/router.py` with no model call:

   | Route | Model | When |
   | --- | --- | --- |
   | fast | `gemini-3.5-flash-lite` | every question by default |
   | strong | `gemini-3.8-flash` | two or more jurisdictions, comparison wording, or more than one question mark |
   | premium | `claude-sonnet-5-5` | the reader asks for it, on the full tier, while Anthropic's spend today is under its cap; past the cap the question goes to strong |
   | lease | `gemini-3.8-flash` | a lease check, on the full tier only |

2. The tier gates routes. On `full`, the deployment runs on a billed Gemini project, so lease checks are allowed. On `free`, lease checks are refused, because free-tier inputs may be used for training. On `static`, no model is called at all.
3. Spend is counted per provider and UTC day, for live calls only (a replayed recording costs nothing), by a `SpendMeter` in Redis that Lane P's kill switch reads as well. The caps are the settings' `*_daily_cap_usd`.
4. Every upload passes a `Redactor` before any model call sees it. Until Lane P's Presidio redactor lands, a stand-in passes the synthetic leases unchanged and refuses everything else.

## Consequences

- The ordinary question costs under a tenth of a cent, and the expensive routes are bounded by their caps and by the tier.
- The strong-route rule is a heuristic. It is measured on the dev set's cross-jurisdiction and multi-article items, and replaced if it misroutes them.
- Checking the cap and then calling is not atomic: concurrent premium requests can overshoot the cap by the cost of the calls in flight, at most a few cents with the configured maximum output.
- "Full tier means billed keys" is an operating rule, not something code can verify: the runbook must say so, and the human confirms it before lease checks go live.

## Alternatives considered

- An LLM classifier choosing the route: an extra call on every question, adding latency and cost to a choice a rule makes well enough. Revisit if the dev set shows misroutes.
- The strong model for everything: about six times the cost per answer, and thinking latency on simple lookups.
- Claude for lease checks (Anthropic does not train on API inputs): it would spend the smaller Anthropic budget. Kept as the fallback if Google's terms change.
- A routing proxy such as LiteLLM or OpenRouter: a dependency, and a hop, for about 150 lines of code; ADR-0006 keeps orchestration thin.
