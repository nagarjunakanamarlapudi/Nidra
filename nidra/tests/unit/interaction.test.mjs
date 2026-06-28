import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import * as R from "../../extension/src/recognizers.js";
import { EVENT_TYPES, makeEvent } from "../../extension/src/schema.js";
import { gate } from "../../extension/src/gate.js";

function page(html, url = "https://example.com/") {
  const dom = new JSDOM(html, { url });
  return dom.window.document;
}

// ---- schema ----
test("EVENT_TYPES includes the new decision types", () => {
  for (const t of ["impression", "interaction", "action"]) {
    assert.ok(EVENT_TYPES.includes(t), `missing ${t}`);
  }
});

test("makeEvent coerces a fractional ts to an integer (history lastVisitTime is a double; backend types ts as int)", () => {
  const ev = makeEvent("pageview", { ts: 1719500000000.5 });
  assert.equal(Number.isInteger(ev.ts), true);
  assert.equal(ev.ts, 1719500000001);
});

// ---- describeInteraction ----
test("describeInteraction maps a toggle to a semantic descriptor", () => {
  const doc = page(
    `<fieldset><legend>Add-ons</legend>
       <label><input type="checkbox" role="switch" checked> Toll pass/Express lane</label>
     </fieldset>`
  );
  const d = R.describeInteraction(doc.querySelector("input"));
  assert.equal(d.control, "toggle");
  assert.equal(d.action, "toggle_on");
  assert.match(d.label, /Toll pass/);
  assert.equal(d.group, "Add-ons");
  assert.equal(d.value, "on");
  assert.equal(d.valueClass, "boolean");
});

test("describeInteraction maps a radio choice as an enum", () => {
  const doc = page(
    `<fieldset><legend>Payment methods</legend>
       <label><input type="radio" name="pm" checked> Apple Pay</label>
     </fieldset>`
  );
  const d = R.describeInteraction(doc.querySelector("input"));
  assert.equal(d.control, "radio");
  assert.equal(d.action, "choose");
  assert.match(d.label, /Apple Pay/);
  assert.equal(d.group, "Payment methods");
  assert.equal(d.valueClass, "enum");
});

// ---- elementKey ----
test("elementKey is stable across re-render/position and bounded", () => {
  const a = page(`<fieldset><legend>Add-ons</legend><label><input id=x type=checkbox> Toll pass</label></fieldset>`);
  const b = page(`<main><div><fieldset><legend>Add-ons</legend><label><input type=checkbox> Toll pass</label></fieldset></div></main>`);
  const k1 = R.elementKey(a.querySelector("input"));
  const k2 = R.elementKey(b.querySelector("input"));
  assert.equal(k1, k2); // semantic signature, not DOM path
  assert.ok(k1.length <= 64);
});

// ---- narrowed redaction (cards + SSNs only; contact details kept) ----
test("redactString keeps phone/DOB, masks only cards + SSNs", () => {
  assert.equal(R.redactString("call (415) 555-1234").redacted, false); // phone kept
  assert.equal(R.redactString("dob 03/14/1990").redacted, false); // date kept
  assert.match(R.redactString("card 4111 1111 1111 1111").value, /\[card\]/);
  assert.equal(R.redactString("nothing here").redacted, false); // no false positives
});

// ---- privacy gate ----
test("gate DROPs a payment instrument label but ALLOWs a method enum", () => {
  const card = gate(
    makeEvent("interaction", {
      data: { control: "radio", group: "Payment methods", label: "Visa ••4242", value: "visa", valueClass: "enum" },
    })
  );
  assert.equal(card, null);

  const applePay = gate(
    makeEvent("interaction", {
      data: { control: "radio", group: "Payment methods", label: "Apple Pay", value: "apple_pay", valueClass: "enum" },
    })
  );
  assert.ok(applePay, "Apple Pay method choice should pass");
  assert.equal(applePay.data.label, "Apple Pay");
});

test("gate DROPs unknown controls and password/credential sections", () => {
  assert.equal(
    gate(makeEvent("interaction", { data: { control: "textbox", group: "Password", label: "Password" } })),
    null
  );
  assert.equal(
    gate(makeEvent("interaction", { data: { control: "radio", group: "Card number", label: "•••• 1111" } })),
    null
  );
});

test("gate scrubs the envelope: strips url query, masks a card in the title, keeps email", () => {
  const ev = gate(
    makeEvent("interaction", {
      url: "https://shop.com/checkout?token=secret123&ref=abc",
      title: "Order for bob@corp.com — card 4111 1111 1111 1111",
      data: { control: "toggle", group: "Add-ons", label: "Toll pass", value: "on", valueClass: "boolean" },
    })
  );
  assert.ok(ev, "safe add-on toggle should pass");
  assert.ok(!/token=secret123/.test(ev.url), "query string must be stripped");
  assert.match(ev.title, /\[card\]/, "card masked in the title");
  assert.doesNotMatch(ev.title, /4111/);
  assert.match(ev.title, /bob@corp\.com/, "email kept (useful signal)");
});
