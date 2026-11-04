# Self-review protocol

Plumbline is reviewed without outside reviewers in this first spiral, so the review has to be designed before the build, not improvised after it. This protocol is that design: what every gold item must record, the rubric applied to the finished work, the answer audit, and the cold test. Every finding, and what was done about it, goes into `docs/review-log.md`.

## 1. The verification record of every gold item

Each answerable item in the golden set carries a `verification` field (`rag_eval.schema.Verification`):

| Field | What it holds |
| --- | --- |
| `quoted_text` | The article text that supports the reference answer, verbatim and in its original language, from the edition the item's `gold_refs` pin; empty only for an item that cites no article (an out-of-scope question). Where a cited source is fetch-only (Dubai's portal forbids redistribution; Colombia's compilation protects its notes) the field holds the export's withheld marker instead of a copy: the checker reads the text, the repository does not carry it |
| `second_source` | Title and URL of a second source that agrees: an official FAQ, government guidance, a bar association pamphlet; empty where no official source covers the item, never a source invented to fill the field |
| `no_second_source` | Set exactly when `second_source` is empty: what was searched and not found, or that the item cites no article |
| `checked_on` | The date of the check |
| `checked_by` | Who checked it |
| `notes` | What the adversarial pass raised and how it was settled |

Rules:

1. The check happens on a different day from the item's authoring, against the official text, never against a summary or a model's answer.
2. The quote comes from the pinned edition. If the official text has changed since, the item is re-pinned to the new edition or moved; a date-conditional item records both texts and its `as_of`.
3. An item that cannot be verified from the official text is dropped or moved to the out-of-scope set.
4. The adversarial pass: a strong model from a different family from the generator is asked to argue against each gold answer. Every disagreement is settled by reading the statute, never by the model, and the outcome is written in `notes` ("challenged: … ; kept, because …" or "changed: …").

## 2. The rubric

Applied to the README, the retrieval core, the evaluation design and `security.md` after a gap of at least 24 hours since the last edit, as three reviewers would. Each question ends as **pass**, **fixed** (with the commit) or **answered in writing** (why it stays).

### A hiring manager at an AI lab, five minutes on the README

1. Does the first screen state the problem, link the live demo and open with the results table?
2. Does every number link to committed JSON, and does `make reproduce` rebuild it at zero API cost?
3. Is the evaluation design visible: a dev and test split, the judge's calibration (TPR and TNR against human labels), confidence intervals, and the naive-RAG and long-context baselines?
4. Are the limitations stated plainly: no lawyer has reviewed it, it gives information and not advice, Arabic is not ingested?
5. Can I tell in five minutes what the author did and what agents drafted (`AI_USAGE.md`)?

### A senior engineer, thirty minutes in the code

1. Does a fresh clone reach a running demo with the documented commands, on an 8 GB machine?
2. Are the core modules small, typed, tested, and readable without their author?
3. Are the boundaries explicit (the contracts in `core/` and `rag_eval.schema`), with no dead code and no unexplained TODOs?
4. Do the tests check behaviour at all four levels, and has the CI evaluation gate demonstrably failed a regression?
5. Do the ADRs state real trade-offs, including what was not built?

### A security reviewer

1. Are retrieved passages and uploads treated as data, never as instructions, and is there a red-team report?
2. Has no secret ever been committed (gitleaks over the full history), and do keys live only in the environment?
3. Is tenant isolation tested, are uploads redacted before any model call, and is model output sanitized before rendering?
4. Are there rate limits, quotas and a spend kill switch, and has the kill switch been triggered by hand?
5. Does `security.md` map each control to the OWASP Top 10 for LLM applications and say what is not covered?

After the human pass, a coding agent applies the same rubric and the OWASP checklist as a separate pass; its findings go into the same log.

## 3. The answer audit

Twenty system answers per jurisdiction, eighty in all, read against the statute. Every error is classified in the failure taxonomy (wrong jurisdiction, cross-lingual miss, article split, numeric or date error, over-abstention, under-abstention, citation mismatch, judge disagreement), and its fix goes through the gate like any other change.

## 4. The cold test

On a device used for nothing else in the build, in a private browser window:

1. Start a screen recording and a timer.
2. Follow only the README: open the live demo, ask one question per jurisdiction, open a citation, try an out-of-scope question, upload a synthetic lease.
3. Then the quickstart from a fresh clone, until `make reproduce` finishes.
4. A screen-reader pass of the demo flow with VoiceOver or NVDA, keyboard only.
5. Watch the recording back, note every hesitation, and fix the top two before Gate 5.

## 5. The second spiral

When budget and time allow, outside reviewers join: a lawyer or law student per jurisdiction, and two outside engineers. Their findings enter through the same `verification` field, the same failure taxonomy, the same review log and the same gate, so nothing in the method changes when they arrive.

## The review log

`docs/review-log.md` is one table, appended to and never edited:

| Date | Pass | Finding | Severity | Resolution | Commit |
| --- | --- | --- | --- | --- | --- |
| 2026-10-19 | (example) senior engineer | `eval/runner.py` mixes I/O and scoring | medium | fixed: scoring moved to pure functions | `abc1234` |
