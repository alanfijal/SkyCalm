import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";

export type ReviewTheme = "dark" | "light";

export async function setReviewTheme(page: Page, theme: ReviewTheme) {
  await page.addInitScript(
    (value) => localStorage.setItem("skycalm-theme", value),
    theme,
  );
}

export async function captureScreen(page: Page, name: string) {
  const width = page.viewportSize()!.width;
  await page.evaluate(() => document.fonts.ready);
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(width);
  if (
    [
      "saved-flights",
      "account",
      "inbox",
      "flight-detail",
      "shared-flight",
      "demo-controls",
      "system-health",
    ].includes(name)
  ) {
    const { violations } = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(
      violations.map((v) => [v.id, ...v.nodes.map((n) => n.target)]),
    ).toEqual([]);
  }
  const directory = process.env.SKYCALM_SCREENS;
  if (!directory) return;
  const theme = await page.locator("html").getAttribute("data-theme");
  await mkdir(directory, { recursive: true });
  await page.screenshot({
    path: join(directory, name + "-" + width + "-" + theme + ".png"),
    animations: "disabled",
    caret: "hide",
  });
}
