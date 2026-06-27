// Nidra local collector — receives activity events from the extension, keeps
// them in memory, derives opinions on demand, and (optionally) serves fixtures.
// Local-only; this is the "your data never leaves the device" mirror.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve, extname } from "node:path";
import { deriveOpinions } from "../extension/src/opinions.js";
import { dream } from "./dreamer.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = resolve(here, "../fixtures");

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "content-type",
};

export function createServer() {
  let events = [];
  let lastDream = null;
  const upsert = (ev) => {
    const i = ev?.id != null ? events.findIndex((e) => e.id === ev.id) : -1;
    if (i >= 0) events[i] = ev;
    else events.push(ev);
  };
  const json = (res, code, obj) => {
    res.writeHead(code, { "content-type": "application/json", ...CORS });
    res.end(JSON.stringify(obj));
  };

  const server = http.createServer(async (req, res) => {
    if (req.method === "OPTIONS") { res.writeHead(204, CORS); res.end(); return; }
    const url = new URL(req.url, "http://localhost");
    try {
      // Ingest — /events, or the connector-shaped path (mirrors how Pragya
      // connectors ingest into the backend).
      if (req.method === "POST" && (url.pathname === "/events" || url.pathname === "/connectors/browser-activity/ingest")) {
        let body = "";
        for await (const c of req) body += c;
        upsert(JSON.parse(body || "{}"));
        json(res, 200, { ok: true, count: events.length });
        return;
      }
      if (req.method === "GET" && url.pathname === "/events") { json(res, 200, events); return; }
      if (req.method === "GET" && url.pathname === "/opinions") { json(res, 200, deriveOpinions(events)); return; }
      if (req.method === "GET" && url.pathname === "/state") { json(res, 200, { events, opinions: deriveOpinions(events) }); return; }
      if (req.method === "POST" && url.pathname === "/clear") { events = []; lastDream = null; json(res, 200, { ok: true }); return; }
      // The dreamer — POST runs a fresh dream over current activity (slow: LLM); GET returns the last dream.
      if (req.method === "POST" && url.pathname === "/dream") { lastDream = await dream(events); json(res, 200, lastDream); return; }
      if (req.method === "GET" && url.pathname === "/dream") {
        json(res, 200, lastDream || { generatedFrom: 0, connectedInsights: [], persona: null, beliefs: [], nextNeeds: [] });
        return;
      }
      if (url.pathname.startsWith("/fixtures/")) {
        const f = resolve(fixturesDir, url.pathname.replace("/fixtures/", ""));
        if (!f.startsWith(fixturesDir)) { res.writeHead(403, CORS); res.end("forbidden"); return; }
        const data = await readFile(f);
        const ext = extname(f);
        const ct = ext === ".html" ? "text/html" : ext === ".json" ? "application/json" : "text/plain";
        res.writeHead(200, { "content-type": ct, ...CORS });
        res.end(data);
        return;
      }
      if (url.pathname === "/") {
        res.writeHead(200, { "content-type": "text/html", ...CORS });
        res.end(`<h1>Nidra collector</h1><p>${events.length} events captured.</p><p><a href="/state">/state</a> · <a href="/opinions">/opinions</a></p>`);
        return;
      }
      res.writeHead(404, CORS);
      res.end("not found");
    } catch (e) {
      json(res, 500, { error: String(e) });
    }
  });

  return { server, getEvents: () => events, clear: () => (events = []) };
}

export function start(port = Number(process.env.PORT || 8799)) {
  const { server, getEvents, clear } = createServer();
  return new Promise((res) =>
    server.listen(port, () => {
      const actual = server.address().port;
      console.log(`Nidra collector on http://localhost:${actual}`);
      res({ server, port: actual, getEvents, clear });
    })
  );
}

// Run directly: `node collector/server.mjs`
if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  start();
}
