// Builds the Nidra extension: generates PNG icons (no external deps) and bundles
// the content script, background service worker, and popup with esbuild.
import { build } from "esbuild";
import { existsSync, readFileSync, writeFileSync, readdirSync, mkdirSync } from "node:fs";
import { deflateSync, deflateRawSync } from "node:zlib";
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

// ---------- bake config: dev reads root .env, prod reads the environment ----------
// An extension can't read .env at runtime (sandboxed), so we inject the backend URL +
// token at build time. Dev defaults to localhost; a prod build (NIDRA_ENV=prod) must
// supply NIDRA_BACKEND_URL so we never ship a localhost URL to the store.
function readEnv(file) {
  const out = {};
  if (!existsSync(file)) return out;
  for (const line of readFileSync(file, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  return out;
}
const mode = process.env.NIDRA_ENV === "prod" ? "prod" : "dev";
const env = readEnv(resolve(root, "../.env"));
let backendUrl, appToken;
if (mode === "prod") {
  backendUrl = process.env.NIDRA_BACKEND_URL;
  appToken = process.env.NIDRA_APP_TOKEN || "";
  if (!backendUrl) {
    console.error("✗ prod build requires NIDRA_BACKEND_URL (e.g. https://api.nidra.app)");
    console.error("  A store-installed extension can't reach localhost — refusing to bake a dev URL.");
    process.exit(1);
  }
  if (!appToken) console.warn("⚠ prod build: NIDRA_APP_TOKEN is empty — baking a blank token.");
} else {
  backendUrl = process.env.NIDRA_BACKEND_URL || `http://localhost:${env.APP_PORT || "8088"}`;
  appToken = process.env.NIDRA_APP_TOKEN || env.API_AUTH_TOKEN || "dev-token";
}
console.log(`✓ ${mode} build · backendUrl=${backendUrl}`);

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

// ---------- package: prod builds emit the store artifact (a plain .zip) ----------
// Hand-rolled ZIP (deflate) — same zero-dep spirit as the PNG encoder above; reuses crc32.
function zipFiles(files) {
  const dosTime = 0, dosDate = (0 << 9) | (1 << 5) | 1; // fixed 1980-01-01 → reproducible artifact
  const locals = [], centrals = [];
  let offset = 0;
  for (const { name, data } of files) {
    const nameBuf = Buffer.from(name, "utf8");
    const crc = crc32(data);
    const comp = deflateRawSync(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0); // local file header
    local.writeUInt16LE(20, 4); // version needed
    local.writeUInt16LE(8, 8); // method: deflate
    local.writeUInt16LE(dosTime, 10);
    local.writeUInt16LE(dosDate, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(comp.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    locals.push(local, nameBuf, comp);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0); // central directory header
    central.writeUInt16LE(20, 4); // version made by
    central.writeUInt16LE(20, 6); // version needed
    central.writeUInt16LE(8, 10); // method: deflate
    central.writeUInt16LE(dosTime, 12);
    central.writeUInt16LE(dosDate, 14);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(comp.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(nameBuf.length, 28);
    central.writeUInt32LE(offset, 42); // offset of local header
    centrals.push(central, nameBuf);
    offset += local.length + nameBuf.length + comp.length;
  }
  const localPart = Buffer.concat(locals);
  const centralPart = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22); // end of central directory
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(files.length, 8);
  eocd.writeUInt16LE(files.length, 10);
  eocd.writeUInt32LE(centralPart.length, 12);
  eocd.writeUInt32LE(localPart.length, 16);
  return Buffer.concat([localPart, centralPart, eocd]);
}

if (mode === "prod") {
  const manifest = JSON.parse(readFileSync(resolve(extDir, "manifest.json"), "utf8"));
  const names = [
    "manifest.json",
    "popup.html",
    "popup.css",
    ...readdirSync(resolve(extDir, "dist")).filter((f) => f.endsWith(".js")).map((f) => `dist/${f}`),
    ...readdirSync(resolve(extDir, "icons")).filter((f) => f.endsWith(".png")).map((f) => `icons/${f}`),
  ];
  const files = names.map((name) => ({ name, data: readFileSync(resolve(extDir, name)) }));
  const outDir = resolve(root, "dist");
  mkdirSync(outDir, { recursive: true });
  const outPath = resolve(outDir, `nidra-${manifest.version}.zip`);
  writeFileSync(outPath, zipFiles(files));
  console.log(`✓ packaged ${files.length} files → ${outPath}`);
  console.log("  ↳ upload this zip to the Chrome Web Store dashboard");
}
