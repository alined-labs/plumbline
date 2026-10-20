# The red team (Lane P, P4)

Two parts, both against the whole path a visitor reaches: the index and its search, the
served Claude configuration, the citation check, and the stream `/api/ask` sends.

1. **The planted poisoned listing**: `python -m plumbline.security.poisoned_listing`
   puts a listing with hidden instructions into the served index and asks three
   questions about it (`apps/api/src/plumbline/security/poisoned_listing.py`).
2. **Promptfoo** (`promptfooconfig.yaml`): the OWASP LLM Top 10 collection, indirect
   prompt injection and RAG poisoning, with Claude Haiku generating the attacks and
   grading the answers. Only static jailbreak templates: an iterative strategy would
   multiply the calls to the served model.

Each run's report goes here as `report-<date>.md`, with the JSON beside it. Nothing in
them is anyone's (the attacks are generated, the answers come from the law), and the
target asks about Florida and Spain only, whose texts may be committed: an answer on
Dubai or Colombian law would quote fetch-only text, which never goes into git.

## Where it runs

On the **rehearsal stack**, never on production: production's spend counters, quotas
and kill switch are the public's, and a red-team run would spend the day's cap. The
rehearsal stack is production's Compose with its own Redis, so its counters start at
zero; its API is reached on the stack's internal network, not through the tunnel, so
the edge's rate limit is not what is tested here (`deploy/edge-check.sh` tests it).

Raise the rehearsal's daily question quota for the run (`DAILY_QUESTIONS_PER_IP=500` in
its override), or most attacks meet a 429 and the report measures the quota instead.

## Running it (the human's shell: the key never reaches a file or a log)

```sh
set -a; source <(sudo grep '^ANTHROPIC_API_KEY=' /etc/plumbline/api.env); set +a
export PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 \
  PROMPTFOO_DISABLE_REMOTE_GENERATION=true PROMPTFOO_DISABLE_SHARING=1
export PLUMBLINE_API=http://127.0.0.1:<the rehearsal API's loopback port>
cd evals/redteam
pnpm dlx promptfoo@0.124.1 redteam generate -c promptfooconfig.yaml -o redteam.yaml
grep -c 'vars:' redteam.yaml          # the number of attacks: state the cost before the next line
pnpm dlx promptfoo@0.124.1 redteam eval -c redteam.yaml -o report-<date>.json
```

Remote generation is off, so the attacks are made by Haiku alone and nothing is sent to
Promptfoo's own servers; a plugin that needs their service is skipped and listed as
skipped in the report.

## Cost, stated before the run

One attack is one answer on the served configuration (A2-claude, about US$0.054,
measured by Lane D on 2026-10-20) plus a Haiku grading (under US$0.01); generating the
attacks is a few Haiku calls per plugin. `numTests: 1` per plugin keeps the run near
one attack per plugin and template: with N attacks counted after `generate`, the run
costs about N x US$0.064. It spends the shared Anthropic key, whose limit is US$25
across every lane, so post N and the cost in the brain before `redteam eval`.
