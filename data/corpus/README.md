# Corpus

`manifest.json` lists every source: one edition of one law, with its URL, retrieval date, sha256 and licence basis (`plumbline.corpus.manifest.Source`). `make check` validates it and checks every committed file's hash.

- `raw/`: sources whose licence allows redistribution, committed.
- `fetched/`: sources fetched at build time by `make fetch` and never committed (the Dubai PDFs). Git ignores this folder; the manifest still pins their hashes.

Lane B owns this folder. `DATA_LICENSES.md` explains each basis.
