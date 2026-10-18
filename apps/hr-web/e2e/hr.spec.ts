import { test, expect } from "@playwright/test";

const email = process.env.E2E_HR_EMAIL ?? "hr@talotrace.ai";
const password = process.env.E2E_HR_PASSWORD ?? "password";

test.beforeEach(async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/roles$/);
});

test("browse from roles to an answer", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Roles" })).toBeVisible();

  await page.locator('a[href^="/roles/"]').first().click();
  await expect(page.getByRole("heading", { name: "Candidates" })).toBeVisible();

  await page.locator('a[href^="/candidates/"]').first().click();
  await expect(page.getByRole("heading", { name: "Candidate" })).toBeVisible();

  await page.locator('a[href^="/answers/"]').first().click();
  await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible();
  await expect(page.getByText("Grading guide")).toBeVisible();
});

test("override a score with a reason", async ({ page }) => {
  await page.locator('a[href^="/roles/"]').first().click();
  await page.locator('a[href^="/candidates/"]').first().click();
  await page.locator('a[href^="/answers/"]').first().click();

  await page.getByLabel("Score").selectOption("4");
  await page.getByLabel("Reason").fill("Measured impact and a clear personal contribution.");
  await page.getByRole("button", { name: "Override score" }).click();

  await expect(page.getByText("Override reason:")).toBeVisible();
  await expect(page.getByText("Final: 4")).toBeVisible();
});

test("failed jobs show the failed status and offer retry", async ({ page }) => {
  await page.goto("/scoring-jobs");
  await expect(page.getByRole("heading", { name: "Scoring jobs" })).toBeVisible();

  const failedRow = page.locator("tr", { hasText: "Failed" }).first();
  if (await failedRow.count()) {
    await expect(failedRow.getByRole("button", { name: /retry/i })).toBeVisible();
  }
});

test("import the data pack", async ({ page }) => {
  const zip = process.env.E2E_PACK_ZIP;
  test.skip(!zip, "Set E2E_PACK_ZIP to the business-systems-pack zip.");

  await page.goto("/import");
  await page.setInputFiles('input[type="file"]', zip as string);
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByText("Import complete")).toBeVisible();
});
