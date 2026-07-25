// k6 load profile used to drive the HPA.
//
// /chat runs TF-IDF retrieval over the document set on every request, so this
// is genuine CPU work in the API container — not an artificial burn endpoint
// added to make the graph move.
//
//   k6 run -e BASE_URL=http://docuchat.localtest.me:8080 scripts/load.js

import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE_URL || "http://docuchat.localtest.me:8080";

// /chat streams its answer token by token with a deliberate 20ms pause between
// tokens (the "typing" effect in the UI), so a single request takes about a
// second of wall time while costing very little CPU. Concurrency, not request
// rate, is therefore the knob that produces CPU pressure here: each request
// still runs a full TF-IDF transform plus cosine similarity before the first
// token goes out.
export const options = {
  stages: [
    { duration: "45s", target: 150 }, // ramp past the 60% CPU target
    { duration: "2m30s", target: 150 }, // hold: the HPA scales out in here
    { duration: "45s", target: 0 },   // ramp down: watch it scale back in
  ],
  thresholds: {
    // The point of the test is that scaling keeps the service healthy while
    // this runs. p95 is generous because the response is a ~1s stream by design.
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<5000"],
  },
};

const QUESTIONS = [
  "how long does shipping take",
  "can I return a used item",
  "how do I reset my password",
  "do you ship to PO boxes",
  "which payment methods do you accept",
  "when do refunds arrive",
];

export default function () {
  const q = QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];
  const res = http.post(
    `${BASE}/api/chat`,
    JSON.stringify({ message: q }),
    { headers: { "Content-Type": "application/json" } },
  );
  check(res, { "status is 200": (r) => r.status === 200 });
  sleep(0.2);
}
