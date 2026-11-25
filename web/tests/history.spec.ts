import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

for (const width of [360, 1440]) {
  test(`route history is readable and keyboard accessible at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/history");
    await expect(
      page.getByRole("heading", { name: "Route history" }),
    ).toBeVisible();
    await expect(page.getByText(/1 matching aircraft report$/)).toBeVisible();
    await expect(page.getByText(/Light reported/)).toBeVisible();
    const details = page.getByText("How reports are matched");
    await details.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText(/within 75 km, 45 minutes/)).toBeVisible();
    await page
      .getByRole("combobox", { name: "Route", exact: true })
      .selectOption("AMS-LHR");
    await expect(page.getByText(/No qualifying aircraft report/)).toBeVisible();
    await expect(
      page.getByLabel("Archived departure").locator("option"),
    ).toHaveCount(5);
    await page.getByLabel("Archived departure").selectOption("gfs-20261124-12");
    await expect(page.getByText(/0 matching aircraft reports/)).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth - innerWidth,
      ),
    ).toBe(0);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
    await page.getByRole("link", { name: /Flight forecast/ }).click();
    await expect(page.getByLabel("Weather source")).toBeAttached();
    await page.getByRole("link", { name: "Route history" }).click();
    await expect(
      page.getByRole("heading", { name: "Post-flight recap" }),
    ).toBeVisible();
  });
}
