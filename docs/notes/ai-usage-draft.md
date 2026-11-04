# Draft: a truthful AI_USAGE.md

Drafted by Lane B on 2026-10-20 for the human to read and edit on Thursday, with the README. `AI_USAGE.md` is the human's own file and no lane may change it; it now contradicts the decision of 2026-10-20 (Claude drafts and verifies the golden set, Gemini cross-checks it, the judge is validated on constructed labels). Everything below the line is the proposed replacement, in the human's voice. The checklist at the end lists the claims a lane outside B should confirm before it is copied over.

---

# How AI is used to build Plumbline

Plumbline is built by one person, Daniel M.C., with Claude as the main tool. This file says what agents draft and check, what I decide and read myself, and how every change is reviewed, so the work can be judged for what it is. No lawyer reviewed any part of it.

## How the build runs

- **Planning and the seed.** The plan, the contracts, the scaffolding of this repository, the drafts of ADR-0001 and ADR-0002 and the self-review protocol were drafted with Claude in a planning conversation. I reviewed and edited them before the first commit.
- **The design system and the logo.** The Alined design system (its tokens, the thirty component specs and the Plumbline logo) was designed with Claude, from interface references I collected, before the build started. A test checks every colour pair for contrast and for colour-vision distance (`DESIGN.md`).
- **Building.** Six Claude Code sessions on four machines each own one part of the system (corpus and benchmark, retrieval and evaluation, generation, API, front end, platform). They coordinate through a private log: each session takes one task at a time, pushes one branch with one commit, and records what it did and why. A planning conversation with Claude reviews held branches when I ask it to.
- **The gate.** A merge queue checks every branch before it reaches `main`: the commit message, a secret scan, which files it may change, a squash onto `main`, and the checks its paths need (linting, strict types, tests at four levels, accessibility). Then CI repeats them on a clean machine.

## What I do myself

- **Decide.** Scope, architecture and every ADR's decision; licence bases; which configuration ships, from the evidence.
- **Read every line of the core.** The chunker, the fusion SQL, the citation verifier, the abstention logic, the judge's calibration, the evaluation runner, the metrics, the statistics and the frozen golden sets are held by the merge queue until I have read every line and approved that exact commit. Other changes merge when the gate passes, and I review them in the pull-request history.
- **Approve the evidence, not produce it.** The benchmark and the judge's labels are made by agents, as the next sections say; I approve the frozen set and run the self-review, the answer audit and the cold test.

## The benchmark

- **Who wrote the items.** Claude (the corpus session) drafted all of the golden set's items: questions, reference answers and the articles they cite. Real questions from official FAQs and public forums seeded some, paraphrased and never copied; the rest are marked `synthetic`. `source_note` on each item says which.
- **Who checked them.** Claude checked each item against the pinned official text as it stood on the item's date, on a different day from drafting, and recorded the quoted passage (withheld for Dubai and Colombia, whose terms forbid a copy) and an official second source where one exists. Gemini (`gemini-3.8-flash`, a different model family) was asked to argue against every reference answer. Every disagreement was settled by reading the statute, never by either model. Each item's `verification` says who checked what and when (`docs/self-review.md`).
- **What that check is worth.** Gemini caught every planted wrong number in a test of the cross-check, but agreed with two wording errors that only the read against the statute found. Agreement between two models is not a lawyer's review, and the dataset card says so.

## The judge

The judge is validated on 100 constructed answers, 50 correct and 50 with planted errors, built by an agent from the golden set. No answer was hand-labelled by me; any labels I add later are reported beside the constructed ones, never mixed in.

## AI inside the product

The site answers with Claude (`claude-sonnet-5-5`) over the retrieved articles; Gemini models answer on the cheaper routes and the configurations the evaluation compares. Answers that Claude generates are judged by Gemini, and Claude Haiku's verdicts are reported beside them, so no model judges its own family alone. Open models running locally embed the statutes. Every call is recorded, so every published number can be replayed without keys.

## What agents never do

Push to `main`, approve their own core modules or a frozen golden set, decide a licence basis, or touch real personal data.

---

## For the human: confirm before copying

1. **The site's model.** Lane D's #159 serves the evaluated Claude configuration (A2-claude); ADR-0007 still routes default questions to `gemini-3.5-flash-lite`. Confirm which model a visitor's answer comes from by default on Thursday, and edit "AI inside the product" to match.
2. **The judges.** From Lane A's A8-q1 note: for Claude-generated runs the primary judge is Lane C's `gemini-3.5-flash-lite` and Haiku is the second; for Gemini-generated runs, confirm with Lane C which judge is primary.
3. **The judge's labels.** "Built by an agent from the golden set" follows C9; confirm with Lane C how the 50 planted errors were made (#158 describes it on /evals).
4. **"No lawyer reviewed"** is true as far as Lane B knows; delete it if that changes.
5. The README links `AI_USAGE.md` for "what is verified by hand"; that phrase should change with this file.
