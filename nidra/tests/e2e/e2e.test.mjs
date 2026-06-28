// End-to-end: load the real extension into Chromium, drive activity across
// search / article / arxiv / gmail / calendar (served at their real hostnames
// via route interception), and assert the collector received correct, redacted
// events and that opinions were formed.
import { test } from "node:test";
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { start } from "../../collector/server.mjs";
import { readFile, mkdtemp } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve, join } from "node:path";
import { tmpdir } from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const EXT = resolve(here, "../../extension");
const FIX = resolve(here, "../../fixtures");

const ROUTES = [
  ["https://www.google.com/search", "google-search.html"],
  ["https://medium.com/", "medium.html"],
  ["https://arxiv.org/", "arxiv.html"],
  ["https://mail.google.com/", "gmail.html"],
  ["https://calendar.google.com/", "gcal.html"],
];

test("e2e: captures activity across sites and forms opinions", { timeout: 120000 }, async () => {
  const collector = await start(0);
  const PORT = collector.port;
  const userDir = await mkdtemp(join(tmpdir(), "nidra-e2e-"));
  const ctx = await chromium.launchPersistentContext(userDir, {
    headless: false,
    args: [
      "--headless=new",
      "--no-sandbox",
      `--disable-extensions-except=${EXT}`,
      `--load-extension=${EXT}`,
      "--no-first-run",
      "--no-default-browser-check",
    ],
  });

  try {
    // Wait for the extension's background service worker, then point it at our
    // ephemeral collector port.
    let [sw] = ctx.serviceWorkers();
    if (!sw) sw = await ctx.waitForEvent("serviceworker", { timeout: 15000 });
    assert.ok(sw, "background service worker should be running");
    await sw.evaluate(async (url) => {
      await chrome.storage.local.set({ nidra_config: { collectorUrl: url, backendUrl: "", paused: false } });
      await chrome.storage.local.set({ nidra_events: [] });
    }, `http://localhost:${PORT}`);

    // Serve fixtures at their real hostnames; let everything else (incl. the
    // collector POST) pass through.
    await ctx.route("**/*", async (route) => {
      const url = route.request().url();
      const hit = ROUTES.find(([p]) => url.startsWith(p));
      if (hit && route.request().resourceType() === "document") {
        return route.fulfill({ status: 200, contentType: "text/html", body: await readFile(resolve(FIX, hit[1]), "utf8") });
      }
      return route.continue();
    });

    const page = await ctx.newPage();
    const visit = async (url) => {
      await page.goto(url, { waitUntil: "domcontentloaded" });
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)).catch(() => {});
      await page.waitForTimeout(1100); // content script emits 'load' at 600ms, then posts
    };

    await visit("https://www.google.com/search?q=raft+consensus+algorithm");
    await visit("https://medium.com/@jane/understanding-raft-consensus-abc123");
    await visit("https://medium.com/@jane/another-raft-post-def456"); // same origin → journey stitches via sessionStorage
    await visit("https://arxiv.org/abs/1404.5326");
    await visit("https://mail.google.com/mail/u/0/#inbox/t-2291");
    await visit("https://calendar.google.com/calendar/u/0/r/week");
    await page.goto("about:blank"); // flush the last page
    await page.waitForTimeout(800);

    // Poll the collector until events arrive (SW posts are async).
    let state;
    for (let i = 0; i < 20; i++) {
      state = await (await fetch(`http://localhost:${PORT}/state`)).json();
      if ((state.events?.length || 0) >= 4) break;
      await new Promise((r) => setTimeout(r, 300));
    }
    const { events, opinions } = state;
    const byType = new Set(events.map((e) => e.type));

    // --- captured the right activity ---
    assert.ok(byType.has("search"), "captured a search");
    assert.ok(byType.has("reading"), "captured article reading");
    assert.ok(byType.has("email"), "captured gmail activity");
    assert.ok(byType.has("calendar"), "captured calendar activity");

    const search = events.find((e) => e.type === "search");
    assert.equal(search.data.query, "raft consensus algorithm");

    const reading = events.filter((e) => e.type === "reading");
    assert.ok(reading.some((e) => e.source === "medium"), "medium classified");
    assert.ok(reading.some((e) => (e.data?.wordCount || 0) > 400), "article word count captured");

    // --- real page content captured (redacted + capped), via @mozilla/readability ---
    const withContent = reading.find((e) => typeof e.data?.content === "string" && e.data.content.length > 50);
    assert.ok(withContent, "reading captured the page's readable text");
    assert.ok(withContent.data.content.length <= 4000, "content is length-capped");
    assert.match(withContent.data.content, /consensus/i, "content is the real article body");

    // --- page-to-page journey stitched within an origin (sessionStorage) ---
    assert.ok(
      reading.some((e) => /understanding-raft-consensus/.test(e.data?.journey?.fromUrl || "")),
      "second same-origin page records where it came from"
    );

    // --- privacy (narrowed): contact details are KEPT as useful signal; only
    //     cards + SSNs are ever masked. The gmail subject keeps the address. ---
    const email = events.find((e) => e.type === "email");
    assert.match(email.data.subject, /Q3 planning/, "gmail subject captured");
    assert.match(email.data.subject, /alice@corp\.com/, "email address kept (signal, not masked)");
    assert.doesNotMatch(JSON.stringify(events), /\b4111\b/, "no card digits leak anywhere");
    assert.doesNotMatch(JSON.stringify(events), /\b\d{3}-\d{2}-\d{4}\b/, "no SSNs leak anywhere");

    const calendar = events.find((e) => e.type === "calendar");
    assert.equal(calendar.data.eventTitle, "Design review with team");

    // --- opinions formed ---
    assert.ok(opinions.counts.total >= 4, "opinions derived from events");
    assert.ok(
      opinions.interests.some((i) => ["raft", "consensus", "paxos"].includes(i.topic)),
      "interest in the right topic"
    );
    assert.ok(opinions.beliefs.length >= 1, "formed at least one belief");

    console.log("\nE2E captured", events.length, "events:", [...byType].join(", "));
    console.log("Top interests:", opinions.interests.slice(0, 4).map((i) => i.topic).join(", "));
    console.log("Beliefs:");
    for (const b of opinions.beliefs) console.log("  •", b.statement, `(${Math.round(b.confidence * 100)}%)`);
  } finally {
    await ctx.close();
    collector.server.close();
  }
});
