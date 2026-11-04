# ADR-0013: Serve every live answer and lease check on Claude, through the evaluated configuration

- Status: proposed
- Date: 2026-10-20
- Replaces: in [ADR-0007](0007-routing-and-spend-caps.md), the choice of model for the served answers and lease checks (its decision 1). Its tiers, spend metering and redaction seam (decisions 2 to 4) stand.

## Context

ADR-0007 routed ordinary questions to Gemini 3.5 Flash-Lite, harder ones to Gemini 3.8 Flash, and lease checks to Gemini 3.8 Flash. Claude Sonnet 5.5 served only a reader who asked for it. By 20 October the Gemini balance was US$4.73, which the golden set's cross-check and the judge's batch runs needed. A day of public answers would have spent it.

The human's instructions on 20 October:

- at about 11:00 UTC: "The problem is with Gemini only will ahve a few dollars, but on Claude API we can spend as fuck, just do it";
- at about 13:43 UTC: "The Antropic limit of the API key is of 25$, and we have at least 100$ as the maximun then don't ask just doit and document everything".

Measured the same day on MX1, for the question "In Florida, how long does a landlord have to return a security deposit when no claim is made on it?" ([cost model](../cost-model.md), section 4):

| Served configuration | Input tokens | Cost |
| --- | ---: | ---: |
| `A2-claude` (SQL retrieval, 8 articles) | 24,418 | US$0.054 |
| `LC-claude` (the whole law, uncached) | 69,257 | US$0.144 |
| `LC-claude`, a repeat question with the law as a cached prefix | | US$0.011 |

## Decision

1. **Claude Sonnet 5.5 serves.** With `ENVIRONMENT=prod`, every live answer and every lease check runs on the premium route (`claude-sonnet-5-5`), whatever route a configuration names (`SERVED_ROUTE` in `api/answering.py`). The Router still decides whether a request may run at all: the demo tier and its refusals are ADR-0007's.
2. **What serves is what was evaluated.** The API loads the Claude twin of `ANSWER_CONFIG` from `evals/configs` (`A2-claude` by default, `LC-claude` without retrieval), so the trace's `config_hash` is the row `/evals` reports. A configuration with no twin on the premium route stops the API at start-up. So does a stand-in pipeline or lease checker in production.
3. **The daily cap holds before every call.** The API reads the day's Anthropic spend from the counters every metered call adds to (`spend:anthropic:<day>`), before each live answer and lease check. At `ANTHROPIC_DAILY_CAP_USD` (US$5.00 in production), it refuses: the answer ends with an error that says when answers resume, and a lease check answers 503. The check runs before each call, so every answer already running when the cap is crossed still finishes: a day can end over the cap by the answers then in flight, about US$0.05 each.
4. **The whole-law path has a size guard.** A long-context question whose jurisdictions' law is over 150,000 tokens (estimated at 3 characters a token, as Claude counted Florida) ends with an error before any model call.
5. **A refusing provider takes the site static.** If the key reaches its spend limit, or is revoked, Anthropic refuses every call. The spend counters then stop growing, so the cap cannot see it. The kill switch ([ADR-0011](0011-security-controls.md), P5, #218) reads the query log instead. When the latest three answers on a live tier all ended with an exception escaping the pipeline, within ten minutes, it takes the tier to `static`. One answer that succeeds in between resets the count. As with the caps, the next UTC day restores the tier and tries the live chat again. The API's own refusals (the cap, the size guard, the tier) record their own sentence, so they never count; a test holds each side (#220, #221).

## Consequences

- An answer costs about US$0.054 instead of a fraction of a cent. The kill switch steps down before the cap: lease checks stop at US$4.00, around the 75th `A2-claude` answer of a day, and the site goes static at US$5.00, around the 93rd ([cost model](../cost-model.md), section 3). It acts within about 40 seconds (its 30-second check and the tier's 10-second cache), so answers started in that window also finish. The key's US$25 limit is shared by production and the lanes' evaluation runs. Until the human raises it toward the US$100 allowed, the lanes keep their combined Claude spend under US$15 (block P5-q2).
- Gemini's remaining balance goes to the golden cross-check and to judging. A Claude answer is judged by Gemini Flash-Lite, a model of another family, with Claude Haiku's verdict beside it (Lane C, C9-q1).
- `/evals` measures the served configuration directly. The Gemini configurations (A0 to A6) stay as the ablation matrix: they are evaluated, not served.
- The size guard binds the whole-law path. On MX1's index of 20 October, the whole law of any one or two of Florida, Spain and Colombia fits under 150,000 tokens (the largest pair, Florida and Spain, is about 140,000). All three do not, so a question naming none of them, which the pipeline reads as every indexed jurisdiction, ends with the guard's error. `A2-claude` is served, so this binds only if `ANSWER_CONFIG` names LC.
- Lease checks were ADR-0007's fallback on Claude ("if Google's terms change"). They are now the default, which also removes the operating rule that the full tier needs a billed Gemini project for lease checks.

## Alternatives considered

- **Keep serving on Gemini.** About US$4.73 would have paid for a few days of answers, and nothing would have been left for the golden set's cross-check and the judge. The human ruled it out.
- **Rename the configuration in code.** The first implementation set the route on the loaded configuration and renamed it `<name>-claude`. Its hash then matched no evaluated row. Lane A's committed twins replaced it the same day, so the trace names exactly what `/evals` measured.
- **Claude Haiku 5.5 to serve.** Lane C measured it about twenty times cheaper on the whole-law path (US$0.007 an answer), but no Haiku configuration has been evaluated. Sonnet is the premium route's model, the one Lane A's judged dev runs measure. A Haiku twin is a configuration to add and evaluate, not a switch to flip.
- **A per-request choice between providers.** It was not needed once Claude's spend was no longer the constraint. Each answer would also have needed its own evaluated row.
