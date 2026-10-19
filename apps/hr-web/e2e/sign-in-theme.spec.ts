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
