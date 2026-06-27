// The Dreamer — Nidra's "Sleep" pass. Where deriveOpinions (heuristic) counts
// tokens, the dreamer asks an LLM to CONNECT signals across the day into
// higher-level intent and a model of the person (e.g. flights + car rental +
// hotel reading = "planning a trip"). Default engine: on-device Gemma 4 via
// Ollama (privacy-first). `callModel` is injectable so tests stay deterministic.

const OLLAMA_HOST = process.env.OLLAMA_HOST || "http://localhost:11434";
const DREAM_MODEL = process.env.NIDRA_DREAM_MODEL || "gemma4:latest";

const SYSTEM = `You are Nidra's "dreamer". While the user sleeps you consolidate their recent online activity.
Your job is to CONNECT THE DOTS ACROSS signals into higher-level understanding — NOT to repeat the activity back.
Look hard for latent intent that spans MULTIPLE signals (e.g. a flight search + a car-rental search + reading about hotels = planning a trip; repeated reading on one topic + a related search = an active project).
Infer interests, reading taste, active projects, and the user's likely next needs. Be specific and confident when several signals corroborate; hedge when the evidence is thin. Never invent activity that isn't in the digest.
Respond with ONLY a JSON object of this exact shape:
{
  "connectedInsights": [{"insight": "one clear sentence", "fromSignals": ["signal", "signal"], "confidence": 0.0, "reasoning": "why these connect"}],
  "persona": "2-3 sentence portrait of who this person is right now",
  "beliefs": [{"statement": "a durable belief about the user", "confidence": 0.0}],
  "nextNeeds": ["a proactive thing Nidra could do next"]
}`;

/** Build the compact, already-redacted text the dreamer reads. */
export function digest(events = []) {
  const by = (t) => events.filter((e) => e.type === t);
  const lines = [];
  const searches = by("search").map((e) => e.data?.query).filter(Boolean);
  if (searches.length) lines.push("SEARCHES:\n" + searches.map((q) => `- ${q}`).join("\n"));

  const reading = by("reading").map((e) => {
    const tags = (e.data?.tags || []).slice(0, 5).join(", ");
    return `- "${e.data?.title || e.title || e.domain}"${e.data?.author ? " by " + e.data.author : ""}${tags ? " (" + tags + ")" : ""} [${e.source}]`;
  });
  if (reading.length) lines.push("READING:\n" + reading.join("\n"));

  const emails = by("email").map((e) => `- ${e.data?.action || "mail"}: ${e.data?.subject || "(no subject)"}`);
  if (emails.length) lines.push("EMAIL:\n" + emails.join("\n"));

  const cal = by("calendar").map((e) => `- ${e.data?.action || "view"}: ${e.data?.eventTitle || "(event)"}`);
  if (cal.length) lines.push("CALENDAR:\n" + cal.join("\n"));

  const domains = {};
  for (const e of events) if (e.domain) domains[e.domain] = (domains[e.domain] || 0) + 1;
  const top = Object.entries(domains).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([d]) => d);
  if (top.length) lines.push("TOP SITES: " + top.join(", "));

  return lines.join("\n\n") || "(no activity captured)";
}

async function ollamaChat(prompt, { host, model }) {
  const res = await fetch(host + "/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      model,
      stream: false,
      format: "json",
      options: { temperature: 0.3 },
      messages: [
        { role: "system", content: SYSTEM },
        { role: "user", content: prompt },
      ],
    }),
  });
  if (!res.ok) throw new Error(`ollama ${res.status}`);
  const data = await res.json();
  return data?.message?.content || "";
}

/** Robustly pull a JSON object out of a model response. */
export function extractJson(text) {
  if (!text) return {};
  let t = String(text).trim().replace(/^```(?:json)?/i, "").replace(/```$/, "").trim();
  try {
    return JSON.parse(t);
  } catch {
    const s = t.indexOf("{");
    const e = t.lastIndexOf("}");
    if (s >= 0 && e > s) {
      try {
        return JSON.parse(t.slice(s, e + 1));
      } catch {
        /* fall through */
      }
    }
    return {};
  }
}

/**
 * Dream over a list of activity events.
 * @param events captured ActivityEvents
 * @param opts.callModel async (prompt) => string — override the engine (tests)
 */
export async function dream(events = [], { callModel, host = OLLAMA_HOST, model = DREAM_MODEL } = {}) {
  const prompt = digest(events);
  const call = callModel || ((p) => ollamaChat(p, { host, model }));
  const parsed = extractJson(await call(prompt));
  return {
    engine: callModel ? "mock" : `ollama:${model}`,
    generatedFrom: events.length,
    connectedInsights: parsed.connectedInsights || parsed.insights || [],
    persona: parsed.persona || null,
    beliefs: parsed.beliefs || [],
    nextNeeds: parsed.nextNeeds || parsed.next_needs || [],
  };
}

/** Is an Ollama-style engine reachable? (used to gate live tests / UI) */
export async function dreamerAvailable({ host = OLLAMA_HOST } = {}) {
  try {
    const res = await fetch(host + "/api/tags", { signal: AbortSignal.timeout(2000) });
    return res.ok;
  } catch {
    return false;
  }
}
