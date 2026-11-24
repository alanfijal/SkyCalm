import { test, expect } from "@playwright/test";

for (const width of [390, 1280]) {
  test(`operator replay updates the route at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 820 });
    await page.goto("http://127.0.0.1:4188/demo");
    await expect(
      page.getByText("Local rehearsal", { exact: true }),
    ).toBeVisible();
    await page.getByLabel("Archived GFS run").selectOption("gfs-20261121-06");
    await page.getByRole("button", { name: "Publish replay" }).click();
    await expect(
      page.getByText("Route updated.", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/69 sample points/)).toBeVisible();
    await expect(
      page.getByRole("img", { name: /Forecast along the route/ }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("link", { name: "Health" }).click();
    await expect(page.getByText("Idle", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Send test event" }),
    ).toBeHidden();
  });
}
