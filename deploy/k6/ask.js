// k6 against /api/ask (Lane P, P8b): 1 question a second for 10 minutes, the load
// docs/cost-model.md section 7 reports. Run it with the pinned image, from the repository
// root, against a stack whose quota allows 600 questions from one address:
//
//   docker run --rm -i --network host -v "$PWD/deploy/k6:/k6:ro" \
//     -e API=http://127.0.0.1:8000 -e QUESTIONS=/k6/questions.json \
//     grafana/k6:2.3.0@sha256:9c2dee7f8ed74d317e4027c06a10f169b625638189de8d4555d0b3486a5aeb34 run /k6/ask.js
//
// QUESTIONS is a JSON array of question strings. Asking the dev split's golden questions
// on a stack in live mode replays their recorded answers, so the run costs nothing and
// measures everything but the model's own latency; a run on new questions spends about
// US$0.0007 each (ADR-0007), US$0.42 for the whole run, and must say so before it starts.
import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const API = __ENV.API || "http://127.0.0.1:8000";
const QUESTIONS = JSON.parse(open(__ENV.QUESTIONS || "/k6/questions.json"));

// The whole answer, first byte to the stream's end: what the reader waits for.
const answer = new Trend("answer_duration", true);

export const options = {
  discardResponseBodies: false,
  scenarios: {
    ask: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.RATE || 1),
      timeUnit: "1s",
      duration: __ENV.DURATION || "10m",
      preAllocatedVUs: 10,
      maxVUs: 40,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    answer_duration: [`p(95)<${__ENV.P95_MS || 6000}`],
  },
};

export default function () {
  const text = QUESTIONS[(__ITER + __VU * 7919) % QUESTIONS.length];
  const body = JSON.stringify({
    id: `k6-${__VU}-${__ITER}`,
    messages: [{ id: "m1", role: "user", parts: [{ type: "text", text }] }],
  });
  const res = http.post(`${API}/api/ask`, body, {
    headers: { "Content-Type": "application/json" },
    timeout: "60s",
  });
  answer.add(res.timings.duration);
  check(res, {
    "status is 200": (r) => r.status === 200,
    "the stream finished": (r) => typeof r.body === "string" && r.body.includes("[DONE]"),
  });
}

// Tried on 2026-10-20 for 20 s on the rehearsal stack's stub pipeline (DURATION=20s): 20
// questions, all 200 with a finished stream, p95 422 ms. The stub paces its words, so this
// proves the harness, not Plumbline's latency; the real run is P8b's, on Friday.
