# HR Sign-In Dark Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the HR app light-themed regardless of the browser or OS color preference so the sign-in labels and form text stay readable in Chrome dark mode.

**Architecture:** Remove the leftover `prefers-color-scheme: dark` palette from the HR app's global stylesheet and declare `color-scheme: light` on `:root`, matching `apps/candidate-web`.
Add a Playwright regression test that emulates both color schemes on `/sign-in` and asserts the computed body, card, heading, label, and input colors.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS v4, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-18-hr-web-design.md`

## Root Cause

`apps/hr-web/app/globals.css` contained the leftover `create-next-app` dark-mode block.
When the browser reported `prefers-color-scheme: dark`, it set `--foreground: #ededed`.
Every HR primitive uses fixed light surfaces such as `bg-white`, and the sign-in labels inherit `--foreground`, so the text became `#ededed` on a white Card.
`apps/candidate-web/app/globals.css` already removed this block and declares `color-scheme: light`, so the HR app was the outlier.

## Global Constraints

- Light-only palette and `color-scheme: light` live in the Locked Decisions (Styling) of `docs/superpowers/specs/2026-10-18-hr-web-design.md`.
- Do not modify `apps/candidate-web`.
- Do not add any dependencies.

## Review Focus

1. Browser or OS dark preference must keep the sign-in heading, labels, and input text at `rgb(23, 23, 23)` on white - pinned by the dark case in Task 1.
2. Browser or OS light preference must render identically to dark preference - pinned by the light case in Task 1.
3. Native form controls must report `color-scheme: light` so Chrome does not darken inputs or autofill - pinned by the `colorScheme` assertion in Task 1.
4. Authenticated pages share the same body variables and fixed white surfaces (Nav, Cards), so the body-level assertions in Task 1 cover the source of their text color.

---

### Task 1: Lock the HR app to the light palette

**Files:**
- Modify: `apps/hr-web/app/globals.css:3-20`
- Test: `apps/hr-web/e2e/sign-in-theme.spec.ts` (create)

**Interfaces:**
- Consumes: the existing `/sign-in` markup, where `main > div` is the Card, and the heading, label, and input elements are the first `h1`, `label span`, and `input` in the document.
- Produces: a document-level `color-scheme: light` contract for every HR page; no runtime API changes.

- [x] **Step 1: Write the failing Playwright test**

Create `apps/hr-web/e2e/sign-in-theme.spec.ts`:

```ts
import { test, expect } from "@playwright/test";

for (const colorScheme of ["light", "dark"] as const) {
  test(`sign-in stays readable with a ${colorScheme} color preference`, async ({ page }) => {
    await page.emulateMedia({ colorScheme });
    await page.goto("/sign-in");

    const colors = await page.evaluate(() => {
      const body = getComputedStyle(document.body);
      const card = getComputedStyle(document.querySelector("main > div")!);
      const heading = getComputedStyle(document.querySelector("h1")!);
      const label = getComputedStyle(document.querySelector("label span")!);
      const input = getComputedStyle(document.querySelector("input")!);

      return {
        bodyBackground: body.backgroundColor,
        bodyColor: body.color,
        cardBackground: card.backgroundColor,
        headingColor: heading.color,
        labelColor: label.color,
        inputColor: input.color,
        colorScheme: getComputedStyle(document.documentElement).colorScheme,
      };
    });

    expect(colors).toEqual({
      bodyBackground: "rgb(255, 255, 255)",
      bodyColor: "rgb(23, 23, 23)",
      cardBackground: "rgb(255, 255, 255)",
      headingColor: "rgb(23, 23, 23)",
      labelColor: "rgb(23, 23, 23)",
      inputColor: "rgb(23, 23, 23)",
      colorScheme: "light",
    });
  });
}
```

- [x] **Step 2: Run the dark case to verify it fails**

Run from `apps/hr-web`:

```bash
npx playwright test e2e/sign-in-theme.spec.ts -g "dark color preference"
```

Expected: FAIL.
The received values include `bodyBackground: "rgb(10, 10, 10)"`, `bodyColor: "rgb(237, 237, 237)"`, `labelColor: "rgb(237, 237, 237)"`, and `colorScheme: "normal"`.

If Chromium is missing, run `npx playwright install chromium` once and repeat.

- [x] **Step 3: Remove the automatic dark palette and lock the document to light**

In `apps/hr-web/app/globals.css`, add `color-scheme: light;` as the first declaration in `:root`, and delete the entire `@media (prefers-color-scheme: dark)` block.
The resulting root and body rules must be:

```css
:root {
  color-scheme: light;
  --background: #ffffff;
  --foreground: #171717;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
}

body {
  background: var(--background);
  color: var(--foreground);
  font-family: Arial, Helvetica, sans-serif;
}
```

Do not change the font declaration or any component classes.

- [x] **Step 4: Run the regression test to verify both schemes pass**

Run from `apps/hr-web`:

```bash
npx playwright test e2e/sign-in-theme.spec.ts
```

Expected: `2 passed`.

- [x] **Step 5: Run the existing unit suite**

Run from `apps/hr-web`:

```bash
npm test
```

Expected: all Vitest tests pass.

- [x] **Step 6: Commit**

```bash
git add apps/hr-web/app/globals.css apps/hr-web/e2e/sign-in-theme.spec.ts
git commit -m "fix(hr-web): keep sign-in readable in dark mode"
```
