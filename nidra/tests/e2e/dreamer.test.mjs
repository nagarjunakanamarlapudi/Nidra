// Live dreamer test: ingest travel activity into the collector, then dream over
// it with the real on-device Gemma engine and assert it connects the signals
// into a travel intent. Skips automatically if Ollama isn't reachable.
import { test } from "node:test";
import assert from "node:assert/strict";
import { start } from "../../collector/server.mjs";
import { dreamerAvailable } from "../../collector/dreamer.mjs";

const TRAVEL = [
  { type: "search", source: "search", domain: "google.com", data: { engine: "google", query: "flights to tokyo march" } },
  { type: "search", source: "search", domain: "google.com", data: { engine: "google", query: "avis car rental shinjuku" } },
  { type: "reading", source: "web", domain: "japan-guide.com", data: { isArticle: true, title: "Best ryokans in Kyoto for 2026", tags: ["japan", "ryokan", "travel"], wordCount: 1200 } },
  { type: "search", source: "search", domain: "google.com", data: { engine: "google", query: "JR pass worth it" } },
  { type: "reading", source: "medium", domain: "medium.com", data: { isArticle: true, title: "Understanding Raft Consensus", tags: ["distributed systems", "raft"], wordCount: 2000 } },
];

test("dreamer connects travel signals via Gemma (live)", { timeout: 180000 }, async (t) => {
  if (!(await dreamerAvailable())) {
    t.skip("Ollama not reachable — skipping live dreamer test");
    return;
  }
  const collector = await start(0);
  const PORT = collector.port;
  try {
    for (const ev of TRAVEL) {
      await fetch(`http://localhost:${PORT}/events`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...ev, id: ev.data.query || ev.data.title, ts: Date.now() }),
      });
    }
    const res = await fetch(`http://localhost:${PORT}/dream`, { method: "POST" });
    const d = await res.json();

    console.log("\nDREAM persona:", d.persona);
    for (const i of d.connectedInsights) console.log("  🔗", i.insight, `(${Math.round((i.confidence || 0) * 100)}%)`);
    for (const n of d.nextNeeds || []) console.log("  → next:", n);

    assert.ok(d.connectedInsights.length >= 1, "dreamer returned at least one connected insight");
    const blob = JSON.stringify(d).toLowerCase();
    assert.match(blob, /trip|travel|japan|tokyo|kyoto|vacation|itinerary/, "connected a travel intent across the signals");
  } finally {
    collector.server.close();
  }
});
