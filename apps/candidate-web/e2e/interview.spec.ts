import { test, expect } from "@playwright/test";

const token = process.env.E2E_CANDIDATE_TOKEN;

test.skip(
  !token,
  "E2E_CANDIDATE_TOKEN not set; a backend with /candidate/* is required",
);

test("answers, confirms, and resumes on the same question", async ({ page }) => {
  await page.goto(`/interview/${token}`);
  await expect(page.getByText("Question 1 of 6")).toBeVisible();
  await page.getByLabel("Your answer").fill("A proud piece of work");
  await page.getByRole("button", { name: "Submit answer" }).click();
  await expect(page.getByText("Your answer has been received")).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Question 2 of 6")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Question 2 of 6")).toBeVisible();
});
