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

// ---- strengthened redaction ----
test("redactString masks phone and date-of-birth shapes", () => {
  assert.match(R.redactString("call (415) 555-1234").value, /\[phone\]/);
  assert.match(R.redactString("dob 03/14/1990").value, /\[date\]/);
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

test("gate scrubs the envelope: strips url query and redacts the title", () => {
  const ev = gate(
    makeEvent("interaction", {
      url: "https://shop.com/checkout?token=secret123&ref=abc",
      title: "Order for bob@corp.com",
      data: { control: "toggle", group: "Add-ons", label: "Toll pass", value: "on", valueClass: "boolean" },
    })
  );
  assert.ok(ev, "safe add-on toggle should pass");
  assert.ok(!/token=secret123/.test(ev.url), "query string must be stripped");
  assert.match(ev.title, /\[email\]/);
});
