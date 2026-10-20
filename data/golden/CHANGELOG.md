# Golden set changelog

One entry per frozen version: what it added, changed or dropped, and why.

## Unreleased

- Schema version 1 defined (`rag_eval.schema.GoldenItem`).
- 60 drafts for v0 in `drafts/golden_v0.jsonl`, not yet verified or frozen.
- 180 drafts for v1 in `drafts/golden_v1.jsonl`: the 60 of v0 and 120 more (single article 54, multi article 25, cross jurisdiction 24, numeric or date-conditional 19, out of scope 25, partial 5, lease check 28), not yet verified or frozen.
- A seeded, stratified dev (120) and test (60) split of v1, in `plumbline.corpus.split`, to be applied when v1 is frozen.
