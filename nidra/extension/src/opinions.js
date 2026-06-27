// Opinions engine: turn a list of activity events into a model of the user.
// Heuristic + deterministic (no randomness; hours computed in UTC) so it is
// fully testable. This is the "understand behavior / form opinions" layer — the
// seam where an LLM "Sleep" pass would later slot in for richer induction.

const STOPWORDS = new Set(
  ("the a an and or but for to of in on at by with from as is are was were be been being this that these those " +
    "how what why when where who which your you i we they it its their our his her how-to your guide best vs how " +
    "new top using use used make made get got into out over under more most less about across una el la los")
    .split(/\s+/)
);

function tokenize(text) {
  if (!text) return [];
  return String(text)
    .toLowerCase()
    .split(/[^a-z0-9+#]+/)
    .filter((w) => w.length >= 3 && !STOPWORDS.has(w) && !/^\d+$/.test(w));
}

function topEntries(map, n) {
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    .slice(0, n);
}

function bump(map, key, by = 1) {
  if (!key) return;
  map.set(key, (map.get(key) || 0) + by);
}

const PRIMARY_HINTS = /arxiv|doi\.org|\.pdf|ieee|acm\.org|nature\.com|sciencedirect|paper/i;
const LISTICLE_RE = /^\s*\d+\s+(things|ways|tips|reasons|tricks|habits|tools)\b/i;

export function deriveOpinions(events = []) {
  const reading = events.filter((e) => e.type === "reading");
  const searches = events.filter((e) => e.type === "search");
  const emails = events.filter((e) => e.type === "email");
  const calendar = events.filter((e) => e.type === "calendar");

  // ---- interests (weighted token frequency across tags/titles/queries) ----
  const interest = new Map();
  const interestEvidence = new Map();
  for (const e of reading) {
    for (const t of e.data?.tags || []) { bump(interest, t, 3); bump(interestEvidence, t); }
    for (const t of tokenize(e.data?.title)) { bump(interest, t, 1); }
  }
  for (const e of searches) {
    for (const t of tokenize(e.data?.query)) { bump(interest, t, 2); bump(interestEvidence, t); }
  }
  const maxScore = Math.max(1, ...interest.values());
  const interests = topEntries(interest, 8).map(([topic, score]) => ({
    topic,
    score: Math.round((score / maxScore) * 100) / 100,
    evidence: interestEvidence.get(topic) || 0,
  }));

  // ---- reading taste ----
  const words = reading.map((e) => e.data?.wordCount || 0).filter(Boolean);
  const readPcts = reading.map((e) => e.metrics?.readPct).filter((x) => typeof x === "number");
  const avgWords = words.length ? Math.round(words.reduce((a, b) => a + b, 0) / words.length) : 0;
  const avgReadPct = readPcts.length
    ? Math.round((readPcts.reduce((a, b) => a + b, 0) / readPcts.length) * 100) / 100
    : null;
  const longForm = words.filter((w) => w > 1000).length;
  const primaryCount = reading.filter(
    (e) => PRIMARY_HINTS.test(e.url || "") || PRIMARY_HINTS.test(e.source || "")
  ).length;
  const listicleCount = reading.filter((e) => LISTICLE_RE.test(e.data?.title || "")).length;

  const authorMap = new Map();
  const sourceMap = new Map();
  for (const e of reading) {
    bump(authorMap, e.data?.author);
    bump(sourceMap, e.source || e.domain);
  }

  const readingTaste = {
    articlesRead: reading.length,
    avgWords,
    avgReadPct,
    longFormRatio: reading.length ? Math.round((longForm / reading.length) * 100) / 100 : 0,
    prefersPrimarySources: primaryCount > listicleCount && primaryCount > 0,
    listicleAversion: listicleCount === 0 && reading.length >= 3,
    topAuthors: topEntries(authorMap, 5).map(([author, count]) => ({ author, count })),
    topSources: topEntries(sourceMap, 5).map(([source, count]) => ({ source, count })),
  };

  // ---- active projects: a topic seen across BOTH search AND reading ----
  const inReading = new Set();
  for (const e of reading) {
    (e.data?.tags || []).forEach((t) => inReading.add(t));
    tokenize(e.data?.title).forEach((t) => inReading.add(t));
  }
  const inSearch = new Set();
  for (const e of searches) tokenize(e.data?.query).forEach((t) => inSearch.add(t));
  const crossTopics = [...inSearch].filter((t) => inReading.has(t));
  const activeProjects = crossTopics
    .map((t) => ({ label: t, evidence: (interestEvidence.get(t) || 0), crossSignal: true }))
    .sort((a, b) => b.evidence - a.evidence || (a.label < b.label ? -1 : 1))
    .slice(0, 5);

  // ---- routines: activity by UTC hour ----
  const byHour = {};
  for (const e of events) {
    const h = new Date(e.ts).getUTCHours();
    byHour[h] = (byHour[h] || 0) + 1;
  }
  const peakHours = Object.entries(byHour)
    .sort((a, b) => b[1] - a[1] || Number(a[0]) - Number(b[0]))
    .slice(0, 3)
    .map(([h]) => Number(h));

  // ---- natural-language beliefs (with confidence + provenance) ----
  const beliefs = [];
  const conf = (n, ceil) => Math.min(1, Math.round((n / ceil) * 100) / 100);

  if (interests[0]) {
    beliefs.push({
      statement: `Actively interested in "${interests[0].topic}"`,
      confidence: conf(interests[0].evidence, 4),
      evidence: interests[0].evidence,
      provenance: ["reading.tags", "search.query"],
    });
  }
  if (activeProjects[0]) {
    beliefs.push({
      statement: `Currently researching "${activeProjects[0].label}" (searched it AND read about it)`,
      confidence: conf(activeProjects[0].evidence + 1, 3),
      evidence: activeProjects[0].evidence,
      provenance: ["search", "reading"],
    });
  }
  if (readingTaste.articlesRead >= 2) {
    const lf = readingTaste.longFormRatio >= 0.5;
    beliefs.push({
      statement: lf
        ? `Prefers long-form reading (avg ~${avgWords} words/article)`
        : `Prefers shorter reads (avg ~${avgWords} words/article)`,
      confidence: conf(readingTaste.articlesRead, 4),
      evidence: readingTaste.articlesRead,
      provenance: ["reading.wordCount"],
    });
  }
  if (readingTaste.prefersPrimarySources) {
    beliefs.push({
      statement: "Trusts primary sources over listicles",
      confidence: conf(primaryCount, 3),
      evidence: primaryCount,
      provenance: ["reading.url"],
    });
  }
  if (readingTaste.topAuthors[0]?.author && readingTaste.topAuthors[0].count >= 2) {
    beliefs.push({
      statement: `Follows the author "${readingTaste.topAuthors[0].author}"`,
      confidence: conf(readingTaste.topAuthors[0].count, 3),
      evidence: readingTaste.topAuthors[0].count,
      provenance: ["reading.author"],
    });
  }
  if (calendar.length || emails.length) {
    beliefs.push({
      statement: `Manages work via webmail/calendar (${emails.length} mail + ${calendar.length} calendar signals)`,
      confidence: conf(emails.length + calendar.length, 4),
      evidence: emails.length + calendar.length,
      provenance: ["email", "calendar"],
    });
  }

  return {
    generatedFrom: events.length,
    counts: {
      reading: reading.length,
      search: searches.length,
      email: emails.length,
      calendar: calendar.length,
      total: events.length,
    },
    interests,
    readingTaste,
    activeProjects,
    routines: { byHour, peakHours },
    beliefs,
  };
}
