import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { captureScreen, setReviewTheme } from "./screenReview";

async function accessible(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(
    violations.map((v) => [v.id, ...v.nodes.map((n) => n.target)]),
  ).toEqual([]);
}

for (const width of [390, 1280])
  for (const theme of ["dark", "light"] as const) {
    test("public screens at " + width + "px in " + theme, async ({ page }) => {
      test.setTimeout(130000);
      await page.setViewportSize({ width, height: 850 });
      await setReviewTheme(page, theme);
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1 })).toContainText(
        "flight may feel",
      );
      await captureScreen(page, "welcome");
      await accessible(page);
      await page.getByRole("link", { name: "Open replay" }).click();
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        "Catania to Milan Linate",
      );
      if (width > 600)
        await expect(
          page.getByRole("button", { name: "Fit route to map" }),
        ).toBeEnabled();
      await captureScreen(page, "replay");
      await accessible(page);
      if (width < 600) {
        const handle = page.getByRole("button", { name: /Flight details/ });
        await handle.click();
        const range = page.getByRole("slider");
        await range.press("End");
        await expect(range).toHaveValue("110");
        await captureScreen(page, "replay-details");
        await accessible(page);
        await range.press("Escape");
        await expect(handle).toBeFocused();
        await expect(handle).toHaveAttribute("aria-expanded", "false");
        const activate = page.getByRole("button", { name: "Explore globe" });
        await activate.click();
        await expect(
          page.getByRole("button", { name: "Fit route to map" }),
        ).toBeEnabled();
      }
      await page.locator("summary").filter({ hasText: "Map layers" }).click();
      await page.getByRole("checkbox", { name: /Cruise winds/ }).check();
      await expect(page.getByRole("status")).toContainText("GFS winds");
      const light = page.getByRole("checkbox", { name: "Day and night" });
      await light.uncheck();
      await light.check();
      await captureScreen(page, "globe-layers");
      await page.goto("/forecast");
      await expect(page.locator(".legend")).toBeVisible();
      if (width > 600)
        await expect(
          page.getByRole("button", { name: "Fit route to map" }),
        ).toBeEnabled();
      await captureScreen(page, "forecast");
      await accessible(page);
      await page.getByRole("button", { name: "Forecast guide" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await captureScreen(page, "guide");
      await accessible(page);
      await page.keyboard.press("Escape");
      await page.goto("/recordings");
      await expect(
        page.getByRole("link", { name: /Play recording/ }).first(),
      ).toBeVisible();
      await captureScreen(page, "recordings");
      await accessible(page);
      await page.goto("/history");
      await expect(
        page.getByRole("heading", { name: "Post-flight recap" }),
      ).toBeAttached();
      await captureScreen(page, "route-history");
      await accessible(page);
      await page.route("**/config.json", (r) =>
        r.fulfill({
          json: {
            apiOrigin: "",
            auth: {
              domain: "https://login.example",
              issuer: "https://identity.example/pool",
              clientId: "review",
            },
          },
        }),
      );
      await page.goto("/flights");
      await expect(
        page.getByRole("heading", { name: "Your flight updates" }),
      ).toBeVisible();
      await captureScreen(page, "sign-in");
      await accessible(page);
    });
  }

test("the first search carries the flight into the archive without exposing it in the address", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("link", { name: "Skip to flight search" })
    .waitFor({ state: "attached" });
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to flight search" }),
  ).toBeFocused();
  await page.locator("input[name=number]").fill("AZ1704");
  await page.locator("input[name=date]").fill("2026-11-21");
  await page.getByRole("button", { name: "Find my flight" }).click();
  await expect(page).toHaveURL(/\/forecast$/);
  await expect(
    page.getByRole("link", { name: /AZ1704.*Play recording/ }).first(),
  ).toBeVisible();
});

for (const theme of ["dark", "light"] as const)
  test(
    "turbulence remains legible with colour-vision deficiencies in " + theme,
    async ({ page, context }) => {
      await page.setViewportSize({ width: 390, height: 850 });
      await setReviewTheme(page, theme);
      await page.goto("/replay");
      await expect(page.locator(".legend .level-dot")).toHaveCount(4);
      const markers = await page
        .locator(".legend .level-dot")
        .evaluateAll((nodes) =>
          nodes.map((el) => {
            const s = getComputedStyle(el);
            return [
              s.clipPath,
              s.borderRadius,
              s.transform,
              s.outlineStyle,
            ].join(" ");
          }),
        );
      expect(new Set(markers).size).toBe(4);
      const session = await context.newCDPSession(page);
      for (const type of [
        "protanopia",
        "deuteranopia",
        "tritanopia",
        "achromatopsia",
      ] as const) {
        await session.send("Emulation.setEmulatedVisionDeficiency", { type });
        await expect(page.locator(".legend")).toContainText(
          /Smooth.*Light.*Moderate.*Severe/,
        );
        await page.locator(".legend").scrollIntoViewIfNeeded();
        await captureScreen(page, "colour-" + type);
      }
    },
  );
test("the mobile timeline moves the aircraft and adds a seatbelt reminder only at moderate or severe samples", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 850 });
  const sample = await (
    await request.get("/data/recorded-flight/az1704-20261121.json")
  ).json();
  const samples = sample.samples as { category: string }[];
  const rough = samples.findIndex(
    (p) => p.category === "moderate" || p.category === "severe",
  );
  expect(rough).toBeGreaterThan(0);
  await page.goto("/replay");
  await page.getByRole("button", { name: /Flight details/ }).click();
  const range = page.getByRole("slider");
  await range.press("Home");
  await expect(page.locator(".seatbelt-indicator")).toHaveCount(0);
  const marker = page.locator("[data-route-aircraft]");
  const first = await marker.getAttribute("transform");
  await range.fill(String(rough));
  await expect(page.locator(".seatbelt-indicator")).toBeVisible();
  await expect(marker).not.toHaveAttribute("transform", first!);
  await expect(page.locator(".flight-phases")).toContainText(
    /climb.*cruise.*descent/i,
  );
});
