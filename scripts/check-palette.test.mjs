import assert from "node:assert/strict"
import { mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { test } from "node:test"

import { checkSource } from "./check-palette.mjs"

function scan(source, file = "Thing.tsx") {
  return checkSource(source, file).map((v) => v.rule)
}

test("flags a stock color utility", () => {
  assert.deepEqual(scan('<p className="text-slate-500" />'), ["stock-color"])
})

test("flags amber and teal at a step the token layer does not define", () => {
  assert.deepEqual(scan('<p className="bg-amber-50 text-teal-700" />'), [
    "stock-color",
    "stock-color",
  ])
})

test("allows the token steps of amber and teal", () => {
  assert.deepEqual(
    scan('<p className="bg-amber-600 bg-amber-100 text-teal-600 bg-teal-100" />'),
    [],
  )
})

test("flags an opacity modifier on a token color", () => {
  assert.deepEqual(scan('<p className="bg-moss-600/10" />'), ["token-alpha"])
})

test("allows an opacity modifier on white", () => {
  assert.deepEqual(scan('<p className="bg-white/10 border-inverse" />'), [])
})

test("flags off-scale radius and shadow", () => {
  assert.deepEqual(scan('<p className="rounded-lg rounded shadow-xl" />'), [
    "off-scale-radius",
    "off-scale-radius",
    "off-scale-shadow",
  ])
})

test("allows the semantic radius and shadow scales", () => {
  assert.deepEqual(scan('<p className="rounded-card shadow-sm shadow-overlay" />'), [])
})

test("flags an arbitrary type size", () => {
  assert.deepEqual(scan('<p className="text-[11px]" />'), ["arbitrary-type"])
})

test("flags a literal color outside tokens.css", () => {
  assert.deepEqual(scan("const c = '#731D2C'", "lib.ts"), ["literal-color"])
})

test("allows literal colors inside tokens.css", () => {
  assert.deepEqual(scan("--crimson-700: #731D2C;", "tokens.css"), [])
})

test("reports the 1-indexed line", () => {
  const [violation] = checkSource('one\ntwo\n<p className="bg-slate-50" />', "Thing.tsx")
  assert.equal(violation.line, 3)
})

test("scanning the real frontend tree returns an array", () => {
  const dir = mkdtempSync(join(tmpdir(), "palette-"))
  writeFileSync(join(dir, "Ok.tsx"), '<p className="text-text-muted" />')
  assert.deepEqual(checkSource('<p className="text-text-muted" />', "Ok.tsx"), [])
})
