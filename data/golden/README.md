# Golden set

The benchmark: English questions over the four jurisdictions' statutes, each with gold article references pinned to a corpus edition, a reference answer, and the record of how it was verified (`rag_eval.schema.GoldenItem`).

- `golden_v<N>.jsonl`: frozen versions, one item per line. A frozen file changes only through a new version, and the merge queue holds it until the human has reviewed every line.
- `drafts/`: candidate items before verification, with `NOTES.md` for the verifier: how the drafts were made, what the build already checks, and where a reading should look hardest.
- `CHANGELOG.md`: what each version added, changed or dropped, and why.

Validate any file with `uv run rag-eval validate <file>`; `make check` validates them all, and also checks that every gold reference's article exists in its pinned file and that every lease-check item agrees with its lease's expected findings. Questions and reference answers are CC BY 4.0.
