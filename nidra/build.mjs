// Builds the Nidra extension: generates PNG icons (no external deps) and bundles
// the content script, background service worker, and popup with esbuild.
import { build } from "esbuild";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { deflateSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = dirname(fileURLToPath(import.meta.url));
const extDir = resolve(root, "extension");

// ---------- minimal PNG encoder (RGBA, no filtering) ----------
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, "ascii");
  const crcBuf = Buffer.alloc(4);
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crcBuf]);
}
function makeIconPng(size) {
  const raw = Buffer.alloc(size * (size * 4 + 1));
  const bg = [79, 70, 229]; // indigo
  const moon = [226, 232, 240]; // pale
  const cBigX = size * 0.44, cBigY = size * 0.5, rBig = size * 0.34;
  const cCutX = size * 0.58, cCutY = size * 0.4, rCut = size * 0.32;
  let p = 0;
  for (let y = 0; y < size; y++) {
    raw[p++] = 0; // filter: none
    for (let x = 0; x < size; x++) {
      const inBig = (x - cBigX) ** 2 + (y - cBigY) ** 2 < rBig * rBig;
      const inCut = (x - cCutX) ** 2 + (y - cCutY) ** 2 < rCut * rCut;
      const isMoon = inBig && !inCut;
      const col = isMoon ? moon : bg;
      raw[p++] = col[0];
      raw[p++] = col[1];
      raw[p++] = col[2];
      raw[p++] = 255;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  return Buffer.concat([
    sig,
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}
for (const size of [16, 48, 128]) {
  writeFileSync(resolve(extDir, "icons", `icon${size}.png`), makeIconPng(size));
}
console.log("✓ icons generated (16/48/128)");

// ---------- bake config from the project's root .env (single source of truth) ----------
// An extension can't read .env at runtime (sandboxed), so we inject APP_PORT +
// API_AUTH_TOKEN at build time. Re-run `npm run build` after editing .env.
function readEnv(file) {
  const out = {};
  if (!existsSync(file)) return out;
  for (const line of readFileSync(file, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  return out;
}
const env = readEnv(resolve(root, "../.env"));
const backendUrl = `http://localhost:${env.APP_PORT || "8088"}`;
const appToken = env.API_AUTH_TOKEN || "dev-token";
console.log(`✓ baked from .env: backendUrl=${backendUrl}`);

// ---------- bundle ----------
await build({
  entryPoints: {
    content: resolve(extDir, "src/content.js"),
    background: resolve(extDir, "src/background.js"),
    popup: resolve(extDir, "src/popup.js"),
  },
  bundle: true,
  format: "iife",
  target: ["chrome110", "safari16"],
  outdir: resolve(extDir, "dist"),
  define: {
    __NIDRA_BACKEND_URL__: JSON.stringify(backendUrl),
    __NIDRA_APP_TOKEN__: JSON.stringify(appToken),
  },
  legalComments: "none",
  logLevel: "info",
});
console.log("✓ bundled content / background / popup");
