import { test } from "node:test";
import assert from "node:assert/strict";
import { deriveOpinions } from "../../extension/src/opinions.js";
import { makeEvent } from "../../extension/src/schema.js";

// Fixed timestamps (UTC) so routines are deterministic across machines.
const T = (h) => Date.UTC(2026, 5, 27, h, 0, 0); // 2026-06-27

function sampleEvents() {
  return [
    makeEvent("reading", {
      ts: T(9), source: "medium", url: "https://medium.com/@jane/raft",
      data: { title: "Understanding Raft Consensus", author: "Jane Doe", wordCount: 2200 },
      metrics: { readPct: 0.9 },
    }),
    makeEvent("reading", {
      ts: T(9), source: "arxiv", url: "https://arxiv.org/abs/1404.5326",
      data: { title: "In Search of an Understandable Consensus Algorithm", author: "Diego Ongaro", wordCount: 8000 },
      metrics: { readPct: 0.4 },
    }),
    makeEvent("reading", {
      ts: T(10), source: "medium", url: "https://medium.com/@jane/paxos",
      data: { title: "Paxos Made Simple", author: "Jane Doe", wordCount: 1500 },
      metrics: { readPct: 0.7 },
    }),
    makeEvent("search", { ts: T(9), source: "search", data: { engine: "google", query: "raft consensus algorithm" } }),
    makeEvent("search", { ts: T(11), source: "search", data: { engine: "google", query: "paxos vs raft tradeoffs" } }),
    makeEvent("email", { ts: T(14), source: "gmail", data: { action: "read", subject: "Q3 planning", participants: 2 } }),
    makeEvent("calendar", { ts: T(14), source: "gcal", data: { action: "create", eventTitle: "Design review" } }),
  ];
}

test("derives interests weighted by titles + queries", () => {
  const o = deriveOpinions(sampleEvents());
  assert.equal(o.generatedFrom, 7);
  const topics = o.interests.map((i) => i.topic);
  assert.ok(topics.includes("consensus"));
  assert.ok(topics.includes("raft"));
  // "raft" appears in a title + both queries (queries weigh 2×) → highest score
  assert.equal(o.interests[0].topic, "raft");
});

test("reading taste: long-form + primary sources + top author", () => {
  const o = deriveOpinions(sampleEvents());
  assert.equal(o.readingTaste.articlesRead, 3);
  assert.ok(o.readingTaste.avgWords > 1000);
  assert.ok(o.readingTaste.longFormRatio >= 0.6);
  assert.equal(o.readingTaste.prefersPrimarySources, true); // arxiv present, no listicles
  assert.equal(o.readingTaste.topAuthors[0].author, "Jane Doe");
});

test("active projects detect cross-signal topics (searched AND read)", () => {
  const o = deriveOpinions(sampleEvents());
  const labels = o.activeProjects.map((p) => p.label);
  assert.ok(labels.includes("raft") || labels.includes("consensus") || labels.includes("paxos"));
  assert.ok(o.activeProjects.every((p) => p.crossSignal === true));
});

test("routines bucket by UTC hour deterministically", () => {
  const o = deriveOpinions(sampleEvents());
  assert.equal(o.routines.byHour[9], 3); // two reading + one search at 09:00 UTC
  assert.ok(o.routines.peakHours.includes(9));
});

test("beliefs are statements with confidence + provenance", () => {
  const o = deriveOpinions(sampleEvents());
  assert.ok(o.beliefs.length >= 3);
  for (const b of o.beliefs) {
    assert.equal(typeof b.statement, "string");
    assert.ok(b.confidence >= 0 && b.confidence <= 1);
    assert.ok(Array.isArray(b.provenance) && b.provenance.length > 0);
  }
  assert.ok(o.beliefs.some((b) => /interested in/.test(b.statement)));
  assert.ok(o.beliefs.some((b) => /primary sources/.test(b.statement)));
});

test("empty input is safe", () => {
  const o = deriveOpinions([]);
  assert.equal(o.generatedFrom, 0);
  assert.deepEqual(o.interests, []);
  assert.deepEqual(o.beliefs, []);
});
