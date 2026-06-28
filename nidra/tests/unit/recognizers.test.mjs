import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";
import * as R from "../../extension/src/recognizers.js";
import * as A from "../../extension/src/analyze.js"; // extractArticle/analyzePage live here (Readability split)

function page(html, url) {
  const dom = new JSDOM(html, { url });
  return { doc: dom.window.document, loc: dom.window.location };
}

// A few real paragraphs so @mozilla/readability scores the page as an article.
const PARA =
  "Consensus is one of the most fundamental and yet most misunderstood problems in distributed systems. " +
  "When a cluster of machines must agree on a single value despite failures, dropped messages, and network " +
  "partitions, the algorithm that coordinates them becomes the beating heart of the system. Raft was designed " +
  "to be understandable, breaking the problem into leader election, log replication, and safety.";
function articleHtml(extra = "", { title = "An Article", author = "", site = "" } = {}) {
  const meta = [
    author ? `<meta name="author" content="${author}">` : "",
    site ? `<meta property="og:site_name" content="${site}">` : "",
  ].join("");
  return `<html><head><title>${title}</title><meta property="og:type" content="article">${meta}</head>
    <body><header><nav>nav</nav></header><article><h1>${title}</h1>
    <p>${PARA}</p><p>${PARA}</p><p>${PARA}</p>${extra ? `<p>${extra}</p>` : ""}
    </article><footer>footer</footer></body></html>`;
}

const mediumFixture = readFileSync(new URL("../../fixtures/medium.html", import.meta.url), "utf8");

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

test("extractSearch pulls and keeps the query (contact details are signal)", () => {
  const { doc, loc } = page("<p>", "https://www.google.com/search?q=raft+consensus+algorithm");
  assert.deepEqual(R.extractSearch(loc, doc), { engine: "google", query: "raft consensus algorithm" });
  // emails are NOT redacted anymore — they're useful signal
  const e = page("<p>", "https://duckduckgo.com/?q=email+me+at+bob@corp.com");
  assert.match(R.extractSearch(e.loc, e.doc).query, /bob@corp\.com/);
  assert.equal(R.extractSearch(page("<p>", "https://medium.com/x").loc, null), null);
});

test("extractArticle parses Readability metadata + redacted, capped content", () => {
  const { doc } = page(mediumFixture, "https://medium.com/@janedoe/raft");
  const a = A.extractArticle(doc);
  assert.equal(a.isArticle, true);
  assert.match(a.title, /Raft/);
  assert.equal(a.author, "Jane Doe");
  assert.equal(a.siteName, "Medium");
  assert.ok(a.wordCount > 400, `wordCount was ${a.wordCount}`);
  assert.equal(typeof a.content, "string");
  assert.ok(a.content.length > 100 && a.content.length <= 4000, `content length ${a.content.length}`);
  assert.match(a.content, /consensus/i); // the real article text, not just metadata
  // dropped junk fields
  assert.equal(a.tags, undefined);
  assert.equal(a.estReadMin, undefined);
});

test("extractArticle prefers cleaned live-story text over video/ad chrome", () => {
  const update =
    "Regional flare-up: Iran's Islamic Revolutionary Guard Corps said it targeted American military sites in neighboring countries after the US struck Iranian sites. " +
    "The US military launched more strikes around the Strait of Hormuz, while US President Donald Trump threatened more military action if Iranian strikes continue. " +
    "Iran's Foreign Ministry said the US strikes were a clear violation of the ceasefire.";
  const html = `<html><head>
    <title>Gulf nations under fire again as US-Iran exchanges escalate | CNN</title>
    <meta property="og:type" content="article">
    <meta property="og:site_name" content="CNN">
    <meta name="author" content="CNN Staff">
    </head><body>
      <section class="layout-live-story-amplify__wrapper">
        <div class="headline_live-story">
          <span>Live Updates</span>
          <h1>Gulf nations under fire again as US-Iran exchanges escalate</h1>
        </div>
        <div class="video-resource">Video Ad Feedback US military conducts strikes against Iranian targets Ad Feedback</div>
        <article class="live-story">
          <article class="live-story-post_pinned liveStoryPost">
            <header><h2 class="live-story-post__headline">Where things stand</h2></header>
            <button>Link Copied!</button>
            <p>${update}</p><p>${update}</p>
          </article>
          <article class="live-story-post liveStoryPost">
            <header><h2 class="live-story-post__headline">Iranian attack a dangerous escalation, Bahrain says</h2></header>
            <button>Link Copied!</button>
            <p>${PARA}</p><p>${PARA}</p>
          </article>
        </article>
      </section>
    </body></html>`;
  const { doc } = page(html, "https://www.cnn.com/2026/06/28/world/live-news/iran-war-strikes-trump");
  const a = A.extractArticle(doc);
  assert.equal(a.isArticle, true);
  assert.match(a.content, /Where things stand/);
  assert.match(a.content, /dangerous escalation/);
  assert.doesNotMatch(a.content, /Video Ad Feedback|Ad Feedback/);
  assert.doesNotMatch(a.content, /Link Copied/);
});

test("extractArticle is false for thin pages", () => {
  const { doc } = page("<html><body><p>hello world</p></body></html>", "https://example.com");
  assert.equal(A.extractArticle(doc).isArticle, false);
});

test("extractArticle content masks cards/SSNs but KEEPS contact details", () => {
  const pii = "Contact Jane Doe at jane@example.com or call 415-555-2671. Card 4111 1111 1111 1111. SSN 123-45-6789.";
  const { doc } = page(articleHtml(pii, { title: "Raft", author: "Jane Doe" }), "https://blog.example/post");
  const a = A.extractArticle(doc);
  assert.equal(a.isArticle, true);
  // masked
  assert.match(a.content, /\[card\]/);
  assert.match(a.content, /\[ssn\]/);
  assert.doesNotMatch(a.content, /4111/);
  assert.doesNotMatch(a.content, /123-45-6789/);
  // kept (signal)
  assert.match(a.content, /jane@example\.com/);
  assert.match(a.content, /415-555-2671/);
  assert.match(a.content, /Jane Doe/);
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
  // gmail scraper is unchanged — its subject still passes through redactString,
  // which now keeps the address (narrowed redaction). Assert the subject survives.
  assert.match(e.subject, /Q3 planning/);
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

test("redactString masks ONLY cards + SSNs, keeps email/phone/name", () => {
  assert.match(R.redactString("card 4111 1111 1111 1111").value, /\[card\]/);
  assert.match(R.redactString("ssn 123-45-6789").value, /\[ssn\]/);
  // a 16-digit run that fails Luhn is NOT a card (e.g. an order id)
  assert.doesNotMatch(R.redactString("order 1234567890123456").value, /\[card\]/);
  // contact details flow through unmasked
  const r = R.redactString("Email jane@example.com or call 415-555-2671");
  assert.equal(r.redacted, false);
  assert.match(r.value, /jane@example\.com/);
  assert.match(r.value, /415-555-2671/);
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

  // a non-sensitive note with an email: captured, not masked
  const note = page('<input type="text" name="note" value="ping bob@corp.com">', "https://x.com");
  const dn = R.describeInput(note.doc.querySelector("input"));
  assert.match(dn.value, /bob@corp\.com/);
  assert.equal(dn.redacted, false);
});

// ----------------------------- flow steps -----------------------------

test("detectStep recognizes a flow from the path keyword", () => {
  const { doc, loc } = page("<html><body><h1>Shipping address</h1></body></html>", "https://shop.com/checkout/shipping");
  const s = R.detectStep(doc, loc);
  assert.ok(s, "checkout path is a flow");
  assert.equal(s.flow, "checkout");
  assert.match(s.label, /Shipping/);
});

test("detectStep reads an explicit 'Step N of M'", () => {
  const { doc, loc } = page(
    `<html><body><nav aria-label="Step"><span>Step 2 of 4</span></nav><h2>Payment</h2></body></html>`,
    "https://app.com/signup"
  );
  const s = R.detectStep(doc, loc);
  assert.ok(s);
  assert.equal(s.index, 2);
  assert.equal(s.of, 4);
  assert.equal(s.flow, "signup"); // sign[\s-]?up matches "signup" in the path
});

test("detectStep reads a small-count progressbar but ignores a 0–100 one", () => {
  const steps = page(
    `<html><body><div role="progressbar" aria-valuenow="3" aria-valuemax="5"></div><h1>Onboarding</h1></body></html>`,
    "https://app.com/onboard"
  );
  const s = R.detectStep(steps.doc, steps.loc);
  assert.equal(s.index, 3);
  assert.equal(s.of, 5);

  // a percentage bar on an ordinary page is NOT a flow step
  const pct = page(
    `<html><body><div role="progressbar" aria-valuenow="60" aria-valuemax="100"></div><h1>Reading</h1></body></html>`,
    "https://example.com/article"
  );
  assert.equal(R.detectStep(pct.doc, pct.loc), null);
});

test("detectStep returns null for an ordinary page", () => {
  const { doc, loc } = page("<html><body><h1>Hello</h1></body></html>", "https://example.com/blog/post");
  assert.equal(R.detectStep(doc, loc), null);
});

test("analyzePage routes to the right event type", () => {
  const search = page("<p>", "https://www.google.com/search?q=foo");
  assert.equal(A.analyzePage(search.doc, search.loc, { ts: 1 }).type, "search");

  const art = page(articleHtml("", { title: "Raft", author: "Jane Doe", site: "Medium" }), "https://medium.com/@x/y");
  const ev = A.analyzePage(art.doc, art.loc, { ts: 2 });
  assert.equal(ev.type, "reading");
  assert.equal(ev.source, "medium");
  assert.equal(typeof ev.data.content, "string");

  const thin = page("<p>hi</p>", "https://example.com");
  assert.equal(A.analyzePage(thin.doc, thin.loc, { ts: 3 }).type, "pageview");
});

test("analyzePage captures app/feed main text without script noise", () => {
  const html = `<html><head><title>Google News</title></head><body>
    <script>window.wiz_progress&&window.wiz_progress();{"@context":"https://schema.org"}</script>
    <header>News Advanced search Help Settings Sign in</header>
    <main>
      <h1>Your briefing</h1>
      <section>
        <h2>Top stories</h2>
        <a href="/read/1">US strikes more targets in Iran as fragile ceasefire comes under renewed strain</a>
        <span>4 hours ago</span>
        <span>CNN</span>
        <a href="/read/2">Live updates: Gulf nations under fire again as US-Iran exchanges escalate</a>
        <span>By Brad Lendon, Jacob Lev and Casey Gannon</span>
      </section>
    </main>
  </body></html>`;
  const { doc, loc } = page(html, "https://news.google.com/home?hl=en-US&gl=US&ceid=US:en");
  const ev = A.analyzePage(doc, loc, { ts: 4 });
  assert.equal(ev.type, "pageview");
  assert.match(ev.data.content, /Your briefing/);
  assert.match(ev.data.content, /Top stories/);
  assert.match(ev.data.content, /Live updates: Gulf nations/);
  assert.doesNotMatch(ev.data.content, /window\.wiz_progress|schema\.org/);
});
