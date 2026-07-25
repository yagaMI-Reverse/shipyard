# E2E testing — structured for AI-assisted QA

This suite is deliberately organized so that an AI agent (Claude Code, Cursor, etc.)
can **safely add tests and repair broken ones** without human babysitting. The rules
below are the contract that makes that possible; the two case studies at the bottom
are real runs against the production deployment.

## Ground rules (the contract)

1. **User-visible locators only.** `getByRole` / `getByText` — never CSS classes,
   never nth-child chains. Classes are styling implementation details and die in
   refactors; accessible names survive.
2. **One user flow per test.** A test reads like the sentence that describes it:
   goto → act → expect what the *user* sees.
3. **Production-safe by construction.** The suite runs against the live deployment
   (`E2E_BASE_URL` to override). Tests may only exercise read paths and additive
   chat flows — nothing destructive, no admin mutations.
4. **Every spec carries its intent in a comment block** — why the flow matters,
   not what the code does. An agent reading the file learns the product, not just
   the selectors.
5. **Assertions check contracts, not pixels.** "A refusal must show zero source
   chips" is a contract; "the badge is grey" is not.

Run it:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e          # all specs × (desktop + Pixel 7)
```

## CI gate

The same suite runs in GitHub Actions ([`.github/workflows/e2e.yml`](../.github/workflows/e2e.yml))
on every push and pull request, against the live deployment — a red suite is a
red check. The Playwright HTML report is uploaded as an artifact on failure, so
a broken run can be debugged straight from the Actions page.

## Case study 1 — AI writes a spec from a plain-English flow description

> **Flow: honest refusal.** When a visitor asks something outside the knowledge
> base, the bot must refuse transparently: refusal text streams in, the answer is
> flagged "not found in documents", and **no source chips render** — a refusal
> that cites documents would be lying about where it looked.

From that description an AI agent produced [`e2e/refusal.spec.ts`](e2e/refusal.spec.ts)
in house style. First run, no edits:

```
Running 2 tests using 2 workers
  ok 1 [desktop] › refusal.spec.ts › off-topic question is refused with no citations (9.2s)
  ok 2 [mobile]  › refusal.spec.ts › off-topic question is refused with no citations (9.8s)
  2 passed (12.1s)
```

## Case study 2 — AI self-heals a selector broken by a UI refactor

A spec written against an old build still used a CSS hook, `button.admin-toggle`.
The class no longer exists. The run fails the way selector rot always fails:

```
Error: locator.click: Test timeout of 15000ms exceeded.
  - waiting for locator('button.admin-toggle')
1 failed
```

The agent read the component source (`src/App.tsx`), found the toggle renders with
the accessible name **Admin**, and applied the smallest possible repair — moving
the locator from a styling detail to a user-visible contract:

```diff
-    await page.locator("button.admin-toggle").click();
+    await page.getByRole("button", { name: /admin/i }).click();
```

```
  ok 1 [desktop] › self-healing demo › admin panel opens (3.7s)
  1 passed (5.3s)
```

The fix follows rule #1, so the healed locator won't rot the same way twice.

## Current status

```
6 flows × (desktop + mobile) = 12 checks — 12 passed (20.6s) against production
```

Chat money-path, suggestion chips, honest refusal (with the no-fake-citations
contract), admin knowledge base, tab switching — plus a Promptfoo regression
suite for the RAG behavior itself in [`../evals/`](../evals/) and Langfuse tracing
on every production call (see the main README).
