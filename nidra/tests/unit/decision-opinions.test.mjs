import { test } from "node:test";
import assert from "node:assert/strict";
import { deriveOpinions } from "../../extension/src/opinions.js";
import { makeEvent } from "../../extension/src/schema.js";

test("deriveOpinions surfaces decision style from interactions/actions", () => {
  const evs = [
    makeEvent("interaction", {
      data: { action: "toggle_on", control: "toggle", label: "Toll pass", group: "Add-ons", elementKey: "toggle:a" },
      metrics: { latencyMs: 1200 },
    }),
    // a reversal on the same control → deliberation signal
    makeEvent("interaction", {
      data: { action: "toggle_off", control: "toggle", label: "Toll pass", group: "Add-ons", elementKey: "toggle:a" },
      metrics: { latencyMs: 1500 },
    }),
    makeEvent("interaction", {
      data: { action: "choose", control: "radio", label: "Apple Pay", group: "Payment methods", elementKey: "radio:b" },
      metrics: { latencyMs: 800 },
    }),
    // Entered a "checkout" flow and advanced a step, but never "submitted" →
    // abandonment is re-derived from the step stream (flow entered, not submitted).
    makeEvent("action", { data: { milestone: "reached", flow: "checkout", stepLabel: "Cart" } }),
    makeEvent("action", { data: { milestone: "advanced", flow: "checkout", stepLabel: "Shipping" } }),
  ];
  const o = deriveOpinions(evs);

  assert.equal(o.counts.interaction, 3);
  assert.equal(o.counts.action, 2);
  assert.ok(o.decisionStyle, "decisionStyle present");
  assert.equal(o.decisionStyle.interactions, 3);
  assert.equal(typeof o.decisionStyle.decisiveness, "number");
  assert.ok(o.decisionStyle.deliberation >= 1, "detected a reversal on the same control");
  assert.ok(o.decisionStyle.abandonmentRate > 0, "inferred an abandoned flow (entered, never submitted)");
  // a decision-style belief is formed
  assert.ok(o.beliefs.some((b) => /decisi|deliberat|abandon/i.test(b.statement)));
});
