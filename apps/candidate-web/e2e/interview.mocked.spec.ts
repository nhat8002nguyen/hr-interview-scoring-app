import { test, expect } from "@playwright/test";

const codes = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"];

function interview(firstAnswered: boolean) {
  return {
    candidate: { id: 1, name: "Nhi Tran", role: "Backend Engineer" },
    questions: codes.map((code, index) => ({
      id: index + 1,
      code,
      sort_order: index + 1,
      prompt: `${code} prompt`,
      answer:
        firstAnswered && index === 0
          ? {
              answer_type: "text",
              text: "A proud piece of work",
              version: 1,
              submitted_at: "2026-09-14T10:15:00Z",
            }
          : null,
      attempts_remaining: 3,
    })),
    progress: { answered: firstAnswered ? 1 : 0, total: 6 },
    max_submissions: 3,
  };
}

test("answers, confirms, advances, and resumes on reload", async ({ page }) => {
  let firstAnswered = false;

  await page.route("**/candidate/interview", (route) =>
    route.fulfill({ json: interview(firstAnswered) }),
  );

  await page.route("**/candidate/interview/answers/**", (route) => {
    firstAnswered = true;
    return route.fulfill({
      status: 201,
      json: {
        status: "received",
        unchanged: false,
        answer: {
          answer_type: "text",
          version: 1,
          submitted_at: "2026-09-14T10:15:00Z",
        },
        attempts_remaining: 2,
      },
    });
  });

  await page.goto("/interview/test-token");
  await expect(page.getByText("Question 1 of 6")).toBeVisible();
  await page.getByLabel("Your answer").fill("A proud piece of work");
  await page.getByRole("button", { name: "Submit answer" }).click();
  await expect(page.getByText("Your answer has been received")).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Question 2 of 6")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Question 2 of 6")).toBeVisible();
});

test("keeps the interview readable in dark mode", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.route("**/candidate/interview", (route) =>
    route.fulfill({ json: interview(false) }),
  );

  await page.goto("/interview/test-token");
  await expect(page.getByText("Question 1 of 6")).toBeVisible();

  const colors = await page.evaluate(() => {
    const style = getComputedStyle(document.body);
    return { background: style.backgroundColor, color: style.color };
  });
  expect(colors.background).toBe("rgb(255, 255, 255)");
  expect(colors.color).toBe("rgb(23, 23, 23)");
});
