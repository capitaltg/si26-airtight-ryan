#!/usr/bin/env node
// Guards the design-token boundary. Tailwind resolves every palette entry to a
// `var(--x)`, which has two consequences this script exists to catch: the stock
// palette still resolves (theme.extend merges rather than replaces, so
// `text-slate-500` renders fine and looks intentional), and an opacity modifier
// on a var() color makes Tailwind 3.4 emit no rule at all — silently. See
// docs/specs/2026-08-04-theming-sitewide-design.md §1.2, §1.3, §3.8.

import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, relative, resolve } from "node:path"
import process from "node:process"

const ROOT = resolve(import.meta.dirname, "..")
const DEFAULT_TARGET = "frontend/src"

const STOCK_SCALES =
  "slate|gray|zinc|neutral|stone|red|orange|yellow|lime|green|emerald|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose"
const PROPS =
  "bg|text|border|ring|ring-offset|from|via|to|divide|outline|decoration|placeholder|fill|stroke|accent|caret|shadow"
const TOKEN_COLORS = "crimson|navy|teal|taupe|sand|moss|amber|status|text"

const RULES = [
  {
    rule: "stock-color",
    // The stock scales, plus amber and teal at any step the token layer does
    // not define — those two keys are the only ones theme.extend partly
    // overrides, so `bg-amber-50` renders a stock value while `bg-amber-600`
    // and `bg-amber-100` render tokens.
    pattern: new RegExp(
      `\\b(?:${PROPS})-(?:(?:${STOCK_SCALES})-\\d{2,3}|amber-(?!(?:600|100)\\b)\\d{2,3}|teal-(?!600\\b)\\d{2,3})\\b`,
      "g",
    ),
    message: "stock Tailwind color — use a token utility (spec §3.2)",
  },
  {
    rule: "token-alpha",
    pattern: new RegExp(`\\b(?:${PROPS})-(?:${TOKEN_COLORS})-[\\w-]+/\\d+`, "g"),
    message: "opacity modifier on a token color emits no CSS at all — use a tint token (spec §1.3)",
  },
  {
    rule: "off-scale-radius",
    pattern: /\brounded(?:-(?:sm|md|lg|xl|2xl|3xl|full))?(?![\w-])/g,
    message: "off-scale radius — use chip/control/block/card/panel/pill (spec §3.3)",
  },
  {
    rule: "off-scale-shadow",
    pattern: /\bshadow-(?:xl|2xl|inner)\b/g,
    message: "off-scale shadow — use xs/sm/md/lg/overlay/focus (spec §3.3)",
  },
  {
    rule: "arbitrary-type",
    pattern: /\btext-\[\d+(?:\.\d+)?px\]/g,
    message: "arbitrary type size — the ramp covers 12–38px (spec §3.4)",
  },
  {
    rule: "literal-color",
    pattern: /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/g,
    message: "literal color outside tokens.css",
  },
]

// `rounded-br-sm` and friends are directional corners, not the radius scale;
// they pair with a `rounded-card` on the same element (the chat bubble tails).
const RADIUS_EXEMPT = /\brounded-(?:t|r|b|l|tl|tr|br|bl|s|e|ss|se|es|ee)-/

export function checkSource(source, file) {
  const isTokens = file.endsWith("tokens.css")
  const lines = source.split("\n")
  const violations = []

  for (const { rule, pattern, message } of RULES) {
    if (rule === "literal-color" && isTokens) continue
    lines.forEach((text, index) => {
      for (const match of text.matchAll(pattern)) {
        if (rule === "off-scale-radius" && RADIUS_EXEMPT.test(match[0])) continue
        violations.push({ rule, message, file, line: index + 1, match: match[0] })
      }
    })
  }

  return violations.sort((a, b) => a.line - b.line)
}

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      yield* walk(path)
    } else if (/\.(?:tsx?|css)$/.test(path)) {
      yield path
    }
  }
}

function collect(targets) {
  const files = []
  for (const target of targets) {
    const path = resolve(ROOT, target)
    if (statSync(path).isDirectory()) files.push(...walk(path))
    else files.push(path)
  }
  return files
}

function main(argv) {
  const warnOnly = argv.includes("--warn")
  const targets = argv.filter((a) => !a.startsWith("--"))
  const files = collect(targets.length > 0 ? targets : [DEFAULT_TARGET])

  let total = 0
  for (const file of files) {
    for (const v of checkSource(readFileSync(file, "utf8"), file)) {
      total += 1
      console.log(`${relative(ROOT, file)}:${v.line}  ${v.rule}  ${v.match} — ${v.message}`)
    }
  }

  if (total === 0) {
    console.log(`check-palette: clean (${files.length} files)`)
  } else {
    console.log(`\ncheck-palette: ${total} violation(s)${warnOnly ? " (warn-only)" : ""}`)
  }
  process.exit(warnOnly || total === 0 ? 0 : 1)
}

// Only the CLI half runs when invoked directly; `checkSource` is imported by
// check-palette.test.mjs, which must not trigger a scan or a process.exit.
if (process.argv[1] && resolve(process.argv[1]) === resolve(import.meta.filename)) {
  main(process.argv.slice(2))
}
