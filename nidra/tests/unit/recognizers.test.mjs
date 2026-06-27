import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import * as R from "../../extension/src/recognizers.js";

function page(html, url) {
  const dom = new JSDOM(html, { url });
  return { doc: dom.window.document, loc: dom.window.location };
}
function lorem(n) {
  const w = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor".split(" ");
  return Array.from({ length: n }, (_, i) => w[i % w.length]).join(" ");
}

test("domainOf strips www", () => {
  assert.equal(R.domainOf("https://www.medium.com/x"), "medium.com");
  assert.equal(R.domainOf("not a url"), null);
});

test("classify routes hosts", () => {
  assert.equal(R.classify(page("<p>", "https://mail.google.com/mail/u/0/#inbox").loc).source, "gmail");
  assert.equal(R.classify(page("<p>", "https://calendar.google.com/calendar/u/0/r/week").loc).source, "gcal");
  assert.equal(R.classify(page("<p>", "https://www.google.com/search?q=hi").loc).source, "search");
  assert.equal(R.classify(page("<p>", "https://medium.com/@x/post").loc).source, "medium");
  assert.equal(R.classify(page("<p>", "https://arxiv.org/abs/1234").loc).source, "arxiv");
  assert.equal(R.classify(page("<p>", "https://example.com/blog").loc).source, "web");
});

test("extractSearch pulls and redacts the query", () => {
  const { doc, loc } = page("<p>", "https://www.google.com/search?q=raft+consensus+algorithm");
  assert.deepEqual(R.extractSearch(loc, doc), { engine: "google", query: "raft consensus algorithm" });
  const e = page("<p>", "https://duckduckgo.com/?q=email+me+at+bob@corp.com");
  assert.match(R.extractSearch(e.loc, e.doc).query, /\[email\]/);
  assert.equal(R.extractSearch(page("<p>", "https://medium.com/x").loc, null), null);
});

test("extractArticle parses metadata + word count", () => {
  const html = `<html><head>
    <title>Understanding Raft | by Jane Doe | Medium</title>
    <meta property="og:type" content="article">
    <meta property="og:title" content="Understanding Raft Consensus">
    <meta property="og:site_name" content="Medium">
    <meta name="author" content="Jane Doe">
    <meta name="keywords" content="distributed systems, consensus, raft, paxos">
    </head><body><article><h1>Understanding Raft Consensus</h1><p>${lorem(500)}</p></article></body></html>`;
  const { doc } = page(html, "https://medium.com/@janedoe/raft");
  const a = R.extractArticle(doc);
  assert.equal(a.isArticle, true);
  assert.equal(a.title, "Understanding Raft Consensus");
  assert.equal(a.author, "Jane Doe");
  assert.ok(a.tags.includes("raft") && a.tags.includes("consensus"));
  assert.ok(a.wordCount > 400);
  assert.ok(a.estReadMin >= 2);
});

test("extractArticle is false for thin pages", () => {
  const { doc } = page("<html><body><p>hello world</p></body></html>", "https://example.com");
  assert.equal(R.extractArticle(doc).isArticle, false);
});

test("extractEmail captures action/subject and redacts addresses", () => {
  const html = `<html><head><title>Gmail</title></head><body>
    <div class="nidra-folder">Inbox</div>
    <h2 class="hP">Re: Q3 planning with alice@corp.com</h2>
    <div data-thread-id="t1"><span class="gD">Alice</span><span class="gD">Bob</span></div>
    </body></html>`;
  const { doc, loc } = page(html, "https://mail.google.com/mail/u/0/#inbox/t1");
  const e = R.extractEmail(doc, loc);
  assert.equal(e.action, "read");
  assert.equal(e.folder, "Inbox");
  assert.equal(e.participants, 2);
  assert.match(e.subject, /\[email\]/);
  assert.doesNotMatch(e.subject, /alice@corp\.com/);
});

test("extractCalendar detects event creation", () => {
  const html = `<html><body><div class="nidra-event-edit">
    <input aria-label="Add title" class="nidra-event-title" value="Dentist appointment">
    <div class="nidra-event-time">Tomorrow 3:00pm</div></div></body></html>`;
  const { doc, loc } = page(html, "https://calendar.google.com/calendar/u/0/r/week");
  const c = R.extractCalendar(doc, loc);
  assert.equal(c.view, "week");
  assert.equal(c.action, "create");
  assert.equal(c.eventTitle, "Dentist appointment");
});

test("redactString masks pii", () => {
  assert.match(R.redactString("reach me at a@b.com").value, /\[email\]/);
  assert.match(R.redactString("card 4111 1111 1111 1111").value, /\[card\]/);
  assert.match(R.redactString("ssn 123-45-6789").value, /\[ssn\]/);
  assert.equal(R.redactString("nothing here").redacted, false);
});

test("input sensitivity + description", () => {
  const pw = page('<input type="password" name="pwd">', "https://x.com");
  assert.equal(R.isSensitiveInput(pw.doc.querySelector("input")), true);
  assert.equal(R.describeInput(pw.doc.querySelector("input")).value, null);

  const card = page('<input type="text" name="cc-number">', "https://x.com");
  assert.equal(R.isSensitiveInput(card.doc.querySelector("input")), true);

  const search = page('<input type="search" name="q" value="raft consensus">', "https://x.com");
  const d = R.describeInput(search.doc.querySelector("input"));
  assert.equal(d.kind, "search");
  assert.equal(d.value, "raft consensus");

  const note = page('<input type="text" name="note" value="ping bob@corp.com">', "https://x.com");
  const dn = R.describeInput(note.doc.querySelector("input"));
  assert.match(dn.value, /\[email\]/);
  assert.equal(dn.redacted, true);
});

test("analyzePage routes to the right event type", () => {
  const search = page("<p>", "https://www.google.com/search?q=foo");
  assert.equal(R.analyzePage(search.doc, search.loc, { ts: 1 }).type, "search");

  const art = page(
    `<html><head><meta property="og:type" content="article"><title>T</title></head><body><article><p>${lorem(
      500
    )}</p></article></body></html>`,
    "https://medium.com/@x/y"
  );
  const ev = R.analyzePage(art.doc, art.loc, { ts: 2 });
  assert.equal(ev.type, "reading");
  assert.equal(ev.source, "medium");

  const thin = page("<p>hi</p>", "https://example.com");
  assert.equal(R.analyzePage(thin.doc, thin.loc, { ts: 3 }).type, "pageview");
});
