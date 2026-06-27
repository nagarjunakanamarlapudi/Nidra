// Popup UI: shows what Nidra has observed and the opinions it has formed.
import { api } from "./browser-api.js";

const $ = (s) => document.querySelector(s);
const ICON = { reading: "📖", search: "🔎", email: "✉️", calendar: "📅", form_input: "⌨️", selection: "✳️", pageview: "🌐" };

function timeAgo(ts) {
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 60) return s + "s ago";
  if (s < 3600) return Math.round(s / 60) + "m ago";
  if (s < 86400) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
}
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function renderOpinions(o) {
  const box = $("#opinions");
  box.innerHTML = "";
  if (!o.generatedFrom) {
    box.append(el("p", "empty", "No signals yet. Browse, search, or read an article — then reopen."));
    return;
  }

  // beliefs
  const bh = el("h3", null, "Opinions formed");
  box.append(bh);
  if (!o.beliefs.length) box.append(el("p", "empty", "Gathering evidence…"));
  for (const b of o.beliefs) {
    const card = el("div", "belief");
    card.append(el("div", "belief-text", b.statement));
    const meta = el("div", "belief-meta");
    const bar = el("div", "bar");
    const fill = el("div", "bar-fill");
    fill.style.width = Math.round(b.confidence * 100) + "%";
    bar.append(fill);
    meta.append(bar, el("span", "ev", `${Math.round(b.confidence * 100)}% · ${b.evidence} signals · ${b.provenance.join(", ")}`));
    card.append(meta);
    box.append(card);
  }

  // interests
  if (o.interests.length) {
    box.append(el("h3", null, "Interests"));
    const chips = el("div", "chips");
    for (const i of o.interests) chips.append(el("span", "chip", `${i.topic} · ${i.evidence}`));
    box.append(chips);
  }

  // reading taste
  const t = o.readingTaste;
  if (t.articlesRead) {
    box.append(el("h3", null, "Reading taste"));
    const ul = el("ul", "taste");
    ul.append(el("li", null, `${t.articlesRead} articles · avg ${t.avgWords} words`));
    ul.append(el("li", null, `Long-form ratio: ${Math.round(t.longFormRatio * 100)}%`));
    if (t.prefersPrimarySources) ul.append(el("li", null, "Prefers primary sources over listicles"));
    if (t.topAuthors[0]?.author) ul.append(el("li", null, `Top author: ${t.topAuthors[0].author}`));
    box.append(ul);
  }
}

function renderSignals(events) {
  const list = $("#signals");
  list.innerHTML = "";
  const recent = [...events].sort((a, b) => b.ts - a.ts).slice(0, 60);
  if (!recent.length) { list.append(el("p", "empty", "Nothing captured yet.")); return; }
  for (const e of recent) {
    const row = el("div", "row");
    row.append(el("span", "ico", ICON[e.type] || "•"));
    const mid = el("div", "mid");
    const label =
      e.type === "search" ? `“${e.data?.query ?? ""}”`
      : e.type === "reading" ? (e.data?.title || e.title || e.domain)
      : e.type === "email" ? `${e.data?.action || "mail"}: ${e.data?.subject || ""}`
      : e.type === "calendar" ? `${e.data?.action || "cal"}: ${e.data?.eventTitle || ""}`
      : e.type === "form_input" ? `${e.data?.kind}: ${e.data?.value ?? "(hidden)"}`
      : e.type === "selection" ? `“${e.data?.text || ""}”`
      : (e.title || e.domain || e.url);
    mid.append(el("div", "label", label || "(page)"));
    mid.append(el("div", "sub", `${e.source}${e.backfill ? " · history" : ""} · ${timeAgo(e.ts)}`));
    row.append(mid);
    if (e.redacted) row.append(el("span", "lock", "🔒"));
    list.append(row);
  }
}

async function refresh() {
  const { events, opinions } = await api.runtime.sendMessage({ type: "nidra-getState" });
  $("#count").textContent = opinions.counts.total;
  $("#breakdown").textContent = `${opinions.counts.reading}📖 ${opinions.counts.search}🔎 ${opinions.counts.email}✉️ ${opinions.counts.calendar}📅`;
  renderOpinions(opinions);
  renderSignals(events);
}

function setPause(paused) {
  const b = $("#pause");
  b.textContent = paused ? "▶ Resume" : "⏸ Pause";
  b.classList.toggle("paused", paused);
  $("#status").textContent = paused ? "paused" : "observing";
  $("#status").classList.toggle("off", paused);
}

function showTab(which) {
  for (const t of ["dreams", "opinions", "signals"]) {
    $("#tab-" + t).classList.toggle("active", which === t);
    $("#" + t).classList.toggle("hidden", which !== t);
  }
}

async function runDream() {
  const out = $("#dream-out");
  out.innerHTML = '<p class="empty">💤 Refreshing opinions, then dreaming on-device — ~10–20s…</p>';
  let cfg = {};
  try { cfg = await api.runtime.sendMessage({ type: "nidra-getConfig" }); } catch {}

  if (cfg.backendUrl) {
    // New pipeline: ground opinions from signals, dream on top, then list dreams.
    const base = cfg.backendUrl.replace(/\/$/, "");
    const headers = cfg.appToken ? { authorization: "Bearer " + cfg.appToken } : {};
    try {
      await fetch(base + "/opinions/refresh", { method: "POST", headers });
      await fetch(base + "/dreams/run", { method: "POST", headers });
      const data = await (await fetch(base + "/dreams", { headers })).json();
      renderDreams(data.dreams || []);
    } catch {
      out.innerHTML =
        '<p class="empty">Couldn\'t reach the dreamer. Run the Pragya backend and make sure Ollama is running.</p>';
    }
    return;
  }

  // Fallback: the local collector's ephemeral dreamer.
  try {
    const url = (cfg.collectorUrl || "http://localhost:8799") + "/dream";
    renderDream(await (await fetch(url, { method: "POST" })).json());
  } catch {
    out.innerHTML =
      '<p class="empty">Couldn\'t reach the dreamer. Run <code>npm run collector</code> and make sure Ollama is running.</p>';
  }
}

function renderDreams(dreams) {
  const out = $("#dream-out");
  out.innerHTML = "";
  if (!dreams.length) {
    out.append(el("p", "empty", "No dreams yet — capture some activity, then dream."));
    return;
  }
  out.append(el("h3", null, "Dreams"));
  for (const d of dreams) {
    const c = el("div", "belief");
    c.append(el("div", "belief-text", "💭 " + d.hypothesis));
    const meta = el("div", "belief-meta");
    const bar = el("div", "bar");
    const fill = el("div", "bar-fill");
    fill.style.width = Math.round((d.confidence || 0) * 100) + "%";
    bar.append(fill);
    meta.append(bar, el("span", "ev", d.kind || ""));
    c.append(meta);
    out.append(c);
  }
}

function renderDream(d) {
  const out = $("#dream-out");
  out.innerHTML = "";
  // Tolerate both the Node mirror (camelCase) and the backend (snake_case).
  const insights = d?.connectedInsights || d?.connected_insights || [];
  const nextNeeds = d?.nextNeeds || d?.next_needs || [];
  if (!d || (!insights.length && !d.persona)) {
    out.append(el("p", "empty", "No dream yet — capture some activity first, then dream."));
    return;
  }
  if (d.persona) {
    const p = el("div", "persona");
    p.append(el("div", "persona-label", "Who you are right now"), el("div", "persona-text", d.persona));
    out.append(p);
  }
  if (insights.length) {
    out.append(el("h3", null, "Connected the dots"));
    for (const i of insights) {
      const c = el("div", "belief");
      c.append(el("div", "belief-text", "🔗 " + i.insight));
      const meta = el("div", "belief-meta");
      const bar = el("div", "bar");
      const fill = el("div", "bar-fill");
      fill.style.width = Math.round((i.confidence || 0) * 100) + "%";
      bar.append(fill);
      meta.append(bar, el("span", "ev", (i.fromSignals || []).join(" + ")));
      c.append(meta);
      if (i.reasoning) c.append(el("div", "sub", i.reasoning));
      out.append(c);
    }
  }
  if (nextNeeds.length) {
    out.append(el("h3", null, "What Nidra could do next"));
    const ul = el("ul", "taste");
    for (const n of nextNeeds) ul.append(el("li", null, n));
    out.append(ul);
  }
  if (d.engine) out.append(el("p", "note", "dreamed by " + d.engine));
}

document.addEventListener("DOMContentLoaded", async () => {
  const cfg = await api.runtime.sendMessage({ type: "nidra-getConfig" });
  setPause(cfg.paused);
  $("#pause").addEventListener("click", async () => {
    const c = await api.runtime.sendMessage({ type: "nidra-setConfig", patch: { paused: !cfg.paused } });
    cfg.paused = c.paused;
    setPause(c.paused);
  });
  $("#clear").addEventListener("click", async () => { await api.runtime.sendMessage({ type: "nidra-clear" }); refresh(); });
  $("#refresh").addEventListener("click", refresh);
  $("#dream").addEventListener("click", runDream);
  $("#tab-dreams").addEventListener("click", () => showTab("dreams"));
  $("#tab-opinions").addEventListener("click", () => showTab("opinions"));
  $("#tab-signals").addEventListener("click", () => showTab("signals"));
  showTab("dreams");
  refresh();
});
