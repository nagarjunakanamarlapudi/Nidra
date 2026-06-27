import { test } from "node:test";
import assert from "node:assert/strict";
import { digest, extractJson, dream } from "../../collector/dreamer.mjs";
import { makeEvent } from "../../extension/src/schema.js";

test("digest groups activity by type", () => {
  const d = digest([
    makeEvent("search", { data: { query: "flights to tokyo" } }),
    makeEvent("reading", { source: "medium", domain: "medium.com", data: { title: "Best ryokans", tags: ["japan", "travel"], author: "A" } }),
    makeEvent("email", { data: { action: "read", subject: "Q3 plan" } }),
  ]);
  assert.match(d, /SEARCHES:/);
  assert.match(d, /flights to tokyo/);
  assert.match(d, /READING:/);
  assert.match(d, /ryokans/);
  assert.match(d, /EMAIL:/);
});

test("extractJson handles fences, noise, and garbage", () => {
  assert.equal(extractJson('```json\n{"a":1}\n```').a, 1);
  assert.equal(extractJson('blah {"b":2} trailing').b, 2);
  assert.deepEqual(extractJson("not json at all"), {});
});

test("dream maps model output (mock engine)", async () => {
  const canned = JSON.stringify({
    connectedInsights: [{ insight: "Planning a trip to Japan", fromSignals: ["flights", "car"], confidence: 0.9, reasoning: "both travel" }],
    persona: "A traveler and systems engineer",
    beliefs: [{ statement: "interested in Japan", confidence: 0.8 }],
    nextNeeds: ["draft a Tokyo itinerary"],
  });
  const out = await dream([makeEvent("search", { data: { query: "flights" } })], { callModel: async () => canned });
  assert.equal(out.engine, "mock");
  assert.equal(out.generatedFrom, 1);
  assert.equal(out.connectedInsights[0].insight, "Planning a trip to Japan");
  assert.equal(out.persona, "A traveler and systems engineer");
  assert.equal(out.beliefs[0].statement, "interested in Japan");
  assert.deepEqual(out.nextNeeds, ["draft a Tokyo itinerary"]);
});

test("dream tolerates the 'insights' alias and bad output", async () => {
  const aliased = await dream([], { callModel: async () => '{"insights":[{"insight":"x"}]}' });
  assert.equal(aliased.connectedInsights[0].insight, "x");
  const garbage = await dream([], { callModel: async () => "the model rambled" });
  assert.deepEqual(garbage.connectedInsights, []);
  assert.equal(garbage.persona, null);
});
