# How AI is used to build Plumbline

Plumbline is built by one person, Daniel M.C., with Claude as the main tool. This file says what agents draft, what I decide and verify myself, and how every change is reviewed, so the work can be judged for what it is.

## How the build runs

- **Planning and the seed.** The plan, the contracts, the scaffolding of this repository, the drafts of ADR-0001 and ADR-0002 and the self-review protocol were drafted with Claude in a planning conversation. I reviewed and edited them before the first commit.
- **The design system and the logo.** The Alined design system (its tokens, the thirty component specs and the Plumbline logo) was designed with Claude, from interface references I collected, before the build started. A test checks every colour pair for contrast and for colour-vision distance ([`DESIGN.md`](DESIGN.md)).
- **Building.** Six Claude Code sessions on four machines each own one part of the system (corpus, retrieval and evaluation, generation, API, front end, platform). They coordinate through a private log: each session takes one task at a time, pushes one branch with one commit, and records what it did and why.
- **The gate.** A merge queue checks every branch before it reaches `main`: the commit message, a secret scan, which files it may change, a squash onto `main`, and the checks its paths need (linting, strict types, tests at four levels, accessibility). Then CI repeats them on a clean machine.

## What I do myself

- **Decide.** Scope, architecture and every ADR's decision; which configuration ships, from the evidence.
- **Read every line of the core.** The chunker, the fusion SQL, the citation verifier, the abstention logic, the judge's calibration, the evaluation runner, the metrics and the statistics are held by the merge queue until I have read every line and approved that exact commit. Other changes merge when the gate passes, and I review them in the pull-request history.
- **Own the evidence.** I verify every gold item of the benchmark against the official text and record how (`docs/self-review.md`); I hand-label the 100 answers that calibrate the judge; I run the self-review, the answer audit and the cold test.

## What agents never do

Push to `main`, approve their own core modules, choose or verify gold answers, label calibration data, decide a licence basis, or touch real personal data.

## AI inside the product

Gemini writes the answers; Claude, a different model family, judges them in the evaluation; open models running locally embed and rerank. Every call is recorded, so every published number can be replayed without keys.

## The benchmark's questions

Questions are written in my own words, paraphrasing real ones from official FAQs and public forums, never copied. Where real questions leave a gap, an LLM drafts a candidate, which is marked `synthetic` in the dataset and verified like any other item.
