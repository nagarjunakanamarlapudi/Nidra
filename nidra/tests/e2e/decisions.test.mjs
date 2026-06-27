// End-to-end: load the real extension into Chromium, drive a checkout-style
// page (toggle an add-on, pick a payment method, click a saved-card instrument),
// and assert the NEW decision capture works through the privacy gate:
//   - interaction events for the add-on toggle + Apple Pay are captured
//   - the saved-card instrument ("Visa ••4242") is DROPPED by the gate
//   - an `action` funnel milestone is captured
//   - everything shares one context_id, and no card digits leak anywhere
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
const CHECKOUT = "https://shop.example/checkout";

test("e2e: decision capture + privacy gate in a real browser", { timeout: 120000 }, async () => {
  const collector = await start(0);
  const PORT = collector.port;
  const userDir = await mkdtemp(join(tmpdir(), "nidra-dec-"));
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
    let [sw] = ctx.serviceWorkers();
    if (!sw) sw = await ctx.waitForEvent("serviceworker", { timeout: 15000 });
    assert.ok(sw, "background service worker should be running");
    await sw.evaluate(async (url) => {
      await chrome.storage.local.set({ nidra_config: { collectorUrl: url, backendUrl: "", paused: false } });
      await chrome.storage.local.set({ nidra_events: [] });
    }, `http://localhost:${PORT}`);

    await ctx.route("**/*", async (route) => {
      if (route.request().url().startsWith(CHECKOUT) && route.request().resourceType() === "document") {
        return route.fulfill({ status: 200, contentType: "text/html", body: await readFile(resolve(FIX, "checkout.html"), "utf8") });
      }
      return route.continue();
    });

    const page = await ctx.newPage();
    await page.goto(CHECKOUT, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(900); // content script arms at ~600ms

    // Drive the decisions.
    await page.click('input[name="toll_pass"]'); // toggle add-on ON
    await page.click('input[value="applepay"]'); // choose a safe payment method
    await page.click('input[value="saved"]'); // a saved-card INSTRUMENT — must be dropped
    await page.fill('input[name="cardNumber"]', "4111 1111 1111 1111"); // sensitive — never captured
    await page.waitForTimeout(500);
    await page.goto("about:blank"); // flush (also triggers abandon, since not submitted)
    await page.waitForTimeout(800);

    let state;
    for (let i = 0; i < 25; i++) {
      state = await (await fetch(`http://localhost:${PORT}/state`)).json();
      if ((state.events || []).some((e) => e.type === "interaction")) break;
      await new Promise((r) => setTimeout(r, 300));
    }
    const events = state.events || [];
    const interactions = events.filter((e) => e.type === "interaction");
    const actions = events.filter((e) => e.type === "action");

    // --- captured the add-on toggle (semantic, not raw) ---
    const toll = interactions.find((e) => /Toll pass/.test(e.data?.label || ""));
    assert.ok(toll, "captured the Toll pass toggle");
    assert.equal(toll.data.action, "toggle_on");
    assert.equal(toll.data.group, "Add-ons");
    assert.equal(toll.data.value, "on");

    // --- captured the safe payment method ---
    assert.ok(interactions.some((e) => /Apple Pay/.test(e.data?.label || "")), "captured Apple Pay choice");

    // --- privacy gate DROPPED the saved-card instrument + the card number ---
    assert.ok(!interactions.some((e) => /4242/.test(JSON.stringify(e.data))), "saved-card instrument dropped");
    assert.doesNotMatch(JSON.stringify(events), /4111/, "card number never captured anywhere");

    // --- funnel milestone + correlation ---
    assert.ok(actions.some((e) => e.data?.milestone), "captured an action milestone");
    assert.ok(toll.context_id, "interaction carries a context_id");
    assert.ok(
      events.filter((e) => e.context_id).every((e) => e.context_id === toll.context_id),
      "all decision events on the page share one context_id"
    );

    console.log("\nE2E decisions captured:", interactions.length, "interactions,", actions.length, "actions");
    console.log("  toll:", JSON.stringify(toll.data));
    console.log("  milestones:", actions.map((a) => a.data.milestone).join(", "));
  } finally {
    await ctx.close();
    collector.server.close();
  }
});
