# e2e

End-to-end smoke tests that drive the running Airtight stack with Playwright
(browser). They confirm the API answers `/health` and the web app renders that
health through the Vite proxy. As real rehearsal flows land, add specs here.

`a11y-contrast.spec.ts` runs axe-core against the home page and fails on any
WCAG 2.1 AA color-contrast violation (success criterion 1.4.3, the 4.5:1 ratio).
Federal software falls under Section 508, which points at WCAG 2.x AA, so this
guards the UI against low-contrast regressions as it grows. It is scoped to the
`color-contrast` rule; widen to a full AA audit by swapping `.withRules` for
`.withTags(["wcag2a", "wcag2aa", "wcag21aa"])`.

## Run it locally

One command boots the stack (docker compose), waits for it, runs the tests, and
tears it down:

```bash
cd e2e
npm install
npm run install:browsers   # first time only: downloads Chromium
npm run e2e
```

Already have the stack running (`docker compose up` from the repo root, or the
dev servers on :8000 and :5173)? Skip the boot and just run the tests:

```bash
cd e2e
npm test
```

Point the tests at a different stack with env vars:

```bash
E2E_WEB_URL=http://localhost:5173 E2E_API_URL=http://localhost:8000 npm test
```

## CI

`.github/workflows/e2e.yml` runs these on every push and pull request: it boots
the stack with docker compose, waits for both services, runs the suite, and
uploads the Playwright HTML report as a build artifact.
