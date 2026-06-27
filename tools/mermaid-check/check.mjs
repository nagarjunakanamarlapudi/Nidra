// Validate every ```mermaid block in Markdown under a directory, using mermaid's
// own parser via jsdom — no browser/chromium needed. Exits non-zero on any
// invalid diagram so CI fails on a broken diagram.
//
// Usage: node check.mjs [docsDir]   (default: docs)

import fs from "node:fs";
import path from "node:path";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><body></body>", { pretendToBeVisual: true });
globalThis.window = dom.window;
globalThis.document = dom.window.document;

const mermaid = (await import("mermaid")).default;
mermaid.initialize({ startOnLoad: false });

function markdownFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...markdownFiles(p));
    else if (entry.name.endsWith(".md")) out.push(p);
  }
  return out;
}

const root = process.argv[2] ?? "docs";
if (!fs.existsSync(root)) {
  console.error(`docs dir not found: ${root}`);
  process.exit(1);
}

let blocks = 0;
let failures = 0;
const re = /```mermaid\n([\s\S]*?)\n```/g;

for (const file of markdownFiles(root)) {
  const text = fs.readFileSync(file, "utf8");
  let match;
  let index = 0;
  while ((match = re.exec(text)) !== null) {
    blocks++;
    index++;
    try {
      await mermaid.parse(match[1]);
    } catch (err) {
      failures++;
      console.error(`✗ ${file} (block ${index}): ${String(err.message).split("\n")[0]}`);
    }
  }
}

console.log(`checked ${blocks} mermaid block(s) under ${root}/`);
if (failures) {
  console.error(`${failures} invalid diagram(s)`);
  process.exit(1);
}
console.log("✓ all diagrams valid");
