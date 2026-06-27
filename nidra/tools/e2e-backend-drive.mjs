// Manual e2e driver: load the real extension, point it at the LIVE Pragya
// backend (not the local collector), drive the checkout fixture, and let the
// events ingest into Postgres. Verify with psql afterwards. Not a unit test —
// run with: node tools/e2e-backend-drive.mjs <backendUrl> <appToken>
import { chromium } from "playwright";
import { readFile, mkdtemp } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve, join } from "node:path";
import { tmpdir } from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const EXT = resolve(here, "../extension");
const FIX = resolve(here, "../fixtures");
const CHECKOUT = "https://shop.example/checkout";

const backendUrl = process.argv[2] || "http://localhost:8088";
const appToken = process.argv[3] || "dev-token";

const userDir = await mkdtemp(join(tmpdir(), "nidra-be-"));
const ctx = await chromium.launchPersistentContext(userDir, {
  headless: false,
  args: [
    "--headless=new", "--no-sandbox",
    `--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`,
    "--no-first-run", "--no-default-browser-check",
  ],
});
try {
  let [sw] = ctx.serviceWorkers();
  if (!sw) sw = await ctx.waitForEvent("serviceworker", { timeout: 15000 });
  await sw.evaluate(async (cfg) => {
    await chrome.storage.local.set({ nidra_config: { ...cfg, collectorUrl: "", paused: false } });
    await chrome.storage.local.set({ nidra_events: [] });
  }, { backendUrl, appToken });

  await ctx.route("**/*", async (route) => {
    if (route.request().url().startsWith(CHECKOUT) && route.request().resourceType() === "document") {
      return route.fulfill({ status: 200, contentType: "text/html", body: await readFile(resolve(FIX, "checkout.html"), "utf8") });
    }
    return route.continue();
  });

  const page = await ctx.newPage();
  await page.goto(CHECKOUT, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(900);
  await page.click('input[name="toll_pass"]');
  await page.click('input[value="applepay"]');
  await page.click('input[value="saved"]');   // instrument — gate should DROP
  await page.fill('input[name="cardNumber"]', "4111 1111 1111 1111"); // sensitive
  await page.waitForTimeout(600);
  await page.goto("about:blank");
  await page.waitForTimeout(1500); // let the SW POST to the backend
  console.log("drove checkout; events posted to", backendUrl);
} finally {
  await ctx.close();
}
