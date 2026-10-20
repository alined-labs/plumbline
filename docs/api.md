# The HTTP API

Everything is under `/api`, so one origin can serve the static front end and the API behind the tunnel. The schema is `GET /api/openapi.json` (a browsable copy at `/api/docs`); `make openapi` writes it to `packages/ts-client/openapi.json` and generates the browser's types from it, and a route or stream payload that changes regenerates both in the same commit. The code is `apps/api/src/plumbline/api/`.

| Route | What it does | Who may call it |
| --- | --- | --- |
| `POST /api/ask` | answers a question as an AI SDK UI message stream | anyone, 30 questions a day by default |
| `POST /api/feedback` | stores a reader's verdict on an answer (204) | anyone |
| `GET /api/usage` | today's questions used, the limit, when it resets | anyone |
| `GET /api/chunks/{id}?quote=` | the article a citation rests on, with where the quote sits in it (only the quote, for a restricted source) | anyone |
| `GET /api/sources/{id}/pages/{n}.png?scale=1..3` | a page of a PDF source as an image (150, 300 or 450 dpi); a placeholder for a restricted source | anyone |
| `GET /api/sources/{id}/pages/{n}/boxes?quote=` | where a quote sits on that page, as fractions of the page | anyone |
| `POST /api/check-lease` | starts a lease check from an uploaded file (202) | anyone, 3 a day by default |
| `GET /api/check-lease/{id}/events` | the check's events as server-sent events | the visitor who started it |
| `GET /api/check-lease/{id}` | the check as it stands, for a page that reloaded | the visitor who started it |
| `GET /api/health`, `GET /api/settings/tier` | version, tier and cache mode; the demo tier | anyone |
| `PUT /api/admin/settings/tier` | sets the demo tier (`full`, `free` or `static`) | admin |
| `GET /api/admin/jobs`, `/jobs/{id}`, `/jobs/{id}/events` | the ingestion jobs and their event streams | admin |
| `GET /api/search` | what retrieval returns for a question, with every score behind each hit | admin |

Admin routes take `Authorization: Bearer <ADMIN_TOKEN>`; with no `ADMIN_TOKEN` set they answer 404, as if they did not exist. `/api/search` returns whole chunks, fetch-only sources included, which is why it is not public.

## Errors

Every error is `application/problem+json` (RFC 9457): `type`, `title`, `status`, a `detail` written for the reader, and, where the status alone does not say which case it is, a stable `code`. A 422 lists each field that failed in `errors`. An unexpected error answers 500 with a fixed detail and is logged in full, never sent.

| `code` | Status | When |
| --- | --- | --- |
| `quota_reached` | 429 | today's questions, or lease checks, are used up; `Retry-After` is the seconds until 00:00 UTC |
| `unsupported_type` | 415 | the upload is not a PDF, a Word document or text, or was sent as a form |
| `too_large` | 413 | the upload is over 10 MB, 80 pages or about 100 pages of text |
| `unreadable` | 422 | no text could be read from the upload: a scan, a broken or protected file |
| `lease_checks_paused` | 503 | the demo tier does not run lease checks (they run only on paid models, which do not train on what is uploaded) |
| `busy` | 503 | a check of the visitor's is still going, or the server is full; `Retry-After` is 30 |
| `not_found` | 404 | no such lease check, it has expired, or it belongs to another visitor |

## Sources whose terms forbid republishing them

The fetch-only sources (the Dubai Legislation Portal's laws and the Dubai Land Department's guide, whose terms forbid making their text available on an online service, and the Senado's annotated Colombian laws, whose editor's notes are protected) are never shown in full. `GET /api/chunks/{id}` returns only the passage a citation quotes as the article's `text` (no heading, no editor's note), with `restricted: true`, and the page routes answer with a labelled placeholder and no boxes. The rule is `api/restricted.py`, and its one switch is flipped only when a publisher has consented, as `DATA_LICENSES.md` records. Florida and Spain are shown in full. `/api/search` returns whole chunks, which is why it is admin-only.

## Visitors and quotas

A browser gets a random visitor id in a signed, `HttpOnly`, `SameSite=Lax` cookie (`plumbline_visitor`, path `/api`, a year) the first time it asks a question or starts a lease check. The signing secret lives in the settings table, so every worker accepts the same cookies. Each question counts against two daily counters in Redis, the visitor's and the address's (an HMAC of it, never the address), which expire at 00:00 UTC; past `DAILY_QUESTIONS_PER_IP` on either, the answer is a 429. Lease checks have counters of their own at a tenth of that, at least one. If Redis cannot count, questions go through and the failure is logged: the spend caps and the kill switch stop runaway cost, and this only rations a fair share.

## Streams

`/api/ask` is an AI SDK UI message stream (`x-vercel-ai-ui-message-stream: v1`): text deltas, plus `data-status`, `data-citation`, `data-answer` and `data-trace` parts, typed from the schema. Whatever happens, the stream ends, with an error part if it has to.

The job and lease-check streams are server-sent events. `event` names the kind, `data` is JSON typed in the schema, and `id` numbers the events from 1: a client that lost its connection sends the last `id` it saw as `Last-Event-ID` and receives what it missed. A comment (`: ping`) every 15 seconds keeps a quiet stream from being closed on the way. A stream ends after its last event: `done` or `failed` for a lease check.

## A lease check

```bash
curl -i -c jar -X POST 'http://localhost:8000/api/check-lease?jurisdiction=florida&signed_on=2026-03-01' \
  -H 'Content-Type: application/pdf' --data-binary @lease.pdf
# 202 {"id": "…"}  and  Location: /api/check-lease/…
curl -N -b jar http://localhost:8000/api/check-lease/<id>/events
```

The lease is the request body, not a multipart form: a form needs a parser dependency and writes its larger parts to a temporary file, while a body is read in memory with the size limit enforced as it arrives. The type comes from the bytes, whatever `Content-Type` says. `jurisdiction` (`dubai`, `spain`, `colombia`, `florida`) and `signed_on` (the law in force on that date) are optional; without a jurisdiction the lease has to name exactly one.

A check emits `stage` events (`uploaded`, `redacting`, `reading`, then `checking` with `done` and `total` clauses), one `finding` per clause worth attention (`Finding` in `leases/schema.py`: severity, title, why, verified citations, confidence), and `done` with the number of findings and the lease's language, or `failed` with a `code` and a message for the reader: `redaction_refused`, `jurisdiction_unknown`, `no_clauses`, `timed_out` (after ten minutes), `interrupted` (the server stopped) or `internal`. There is no score for the whole lease: a lease is not more or less legal, its clauses are.

What happens to the file:

- It is redacted before any model sees any of it; until the redactor is in place, a lease that is not one of the repo's synthetic ones is refused with `redaction_refused`.
- It is never written to disk, never logged and not kept. The check keeps its events (the stages, and the findings, which quote clauses after redaction) in memory for half an hour, for the visitor who started it, so a page can reload; then they are gone. The only things logged are a check's id and the type of an unexpected error, because an error's message can quote the text it choked on.
- At most four checks run at once, and one for a visitor.

Until retrieval and the redactor are wired in, the server answers with a stand-in that finds one clause of each severity in any lease, citing an invented "Stub Act", and says that nothing in its findings is legal information.

## Run it

```bash
make up        # Postgres and Redis
make api       # http://localhost:8000, on the stub pipeline until the real one is wired in
make openapi   # the schema, the stream fixture and the TypeScript client
```
