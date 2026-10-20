# Golden set

The benchmark: English questions over the four jurisdictions' statutes, each with gold article references pinned to a corpus edition, a reference answer, and the record of how it was verified (`rag_eval.schema.GoldenItem`).

- `golden_v<N>.jsonl`: frozen versions, one item per line. A frozen file changes only through a new version, and the merge queue holds it until the human has reviewed every line.
- `drafts/`: candidate items before verification: `golden_v0.jsonl` (60 items) and `golden_v1.jsonl` (180: the same 60, unchanged, and 120 added in v1), with `NOTES.md` for the verifier: how the drafts were made, what the build already checks, and where a reading should look hardest.
- The dev (120) and test (60) split is not in the drafts. It is assigned when v1 is frozen, by `uv run python -m plumbline.corpus.split` (seeded and stratified by category, place and language; `NOTES.md` shows the result as it stands).
- `CHANGELOG.md`: what each version added, changed or dropped, and why.

Validate any file with `uv run rag-eval validate <file>`; `make check` validates them all, and also checks that every gold reference's article exists in its pinned file, that every lease-check item agrees with its lease's expected findings, that a later draft keeps the items of an earlier one unchanged, and that a frozen file is finished: every item verified, none from a later version, and from v1 on every item in dev or test. Questions and reference answers are CC BY 4.0.
