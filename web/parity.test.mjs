// Parity test: runs the JS core from web/app.html against tests/vectors.json.
// Usage: node web/parity.test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "app.html"), "utf8");
const m = html.match(/<script id="core">([\s\S]*?)<\/script>/);
if (!m) { console.error("core script block not found"); process.exit(1); }

const ctx = vm.createContext({ Math, Number, String, Object, Array, Error, isFinite, parseInt, JSON });
vm.runInContext(m[1] + "\n;globalThis.__core = { evaluate, ecdSweep, parseSectionsText, resultsCsv, sweepDips };", ctx);
const core = ctx.__core;
const vectors = JSON.parse(readFileSync(join(here, "..", "tests", "vectors.json"), "utf8"));

const REL = 1e-9;
let checks = 0, failures = 0;

function fail(path, msg) { failures++; console.error(`FAIL ${path}: ${msg}`); }

function compare(expected, actual, path) {
  if (typeof expected === "number") {
    checks++;
    if (typeof actual !== "number") return fail(path, `expected number ${expected}, got ${actual}`);
    const tol = REL * Math.max(1, Math.abs(expected));
    if (Math.abs(expected - actual) > tol) fail(path, `expected ${expected}, got ${actual}`);
    return;
  }
  if (expected === null || typeof expected !== "object") {
    checks++;
    if (expected !== actual) fail(path, `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    return;
  }
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || actual.length !== expected.length) return fail(path, "array length mismatch");
    expected.forEach((e, i) => compare(e, actual[i], `${path}[${i}]`));
    return;
  }
  if (actual === null || typeof actual !== "object") return fail(path, "expected object");
  for (const k of Object.keys(expected)) compare(expected[k], actual[k], `${path}.${k}`);
}

for (const v of vectors.cases) {
  let res;
  try {
    res = core.evaluate(JSON.parse(JSON.stringify(v.input)));
  } catch (e) {
    if (v.error === undefined) { fail(v.name, `unexpected error: ${e.message}`); continue; }
    checks++;
    if (e.name !== "InputError" || e.message !== v.error) fail(v.name, `error "${e.message}" != "${v.error}"`);
    continue;
  }
  if (v.error !== undefined) { fail(v.name, `expected error "${v.error}"`); continue; }
  compare(v.result, JSON.parse(JSON.stringify(res)), v.name);
  if (v.sweep) {
    const sw = JSON.parse(JSON.stringify(core.ecdSweep(v.input)));
    compare(v.sweep, sw, `${v.name}.sweep`);
    if (v.sweep_dips) compare(v.sweep_dips, JSON.parse(JSON.stringify(core.sweepDips(sw))), `${v.name}.sweep_dips`);
  }
  // CSV builder must run cleanly on every valid result.
  const csv = core.resultsCsv(res);
  checks++;
  if (!csv.includes("ecd_ppg,")) fail(v.name, "csv missing ecd row");
}

for (const p of vectors.parse) {
  let rows;
  try {
    rows = core.parseSectionsText(p.text);
  } catch (e) {
    if (p.error === undefined) { fail(`parse.${p.name}`, `unexpected error: ${e.message}`); continue; }
    checks++;
    if (e.message !== p.error) fail(`parse.${p.name}`, `error "${e.message}" != "${p.error}"`);
    continue;
  }
  if (p.error !== undefined) { fail(`parse.${p.name}`, `expected error "${p.error}"`); continue; }
  compare(p.rows, JSON.parse(JSON.stringify(rows)), `parse.${p.name}`);
}

if (failures) {
  console.error(`${failures} failure(s) in ${checks} checks`);
  process.exit(1);
}
console.log(`parity ok: ${vectors.cases.length} cases, ${vectors.parse.length} parse vectors, ${checks} checks, rel tol ${REL}`);
