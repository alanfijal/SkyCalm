import { test, expect } from "@playwright/test";
import type { Sample } from "../src/types";

test("missing forecast data and an unclassified aircraft report have distinct explanations", async ({
  page,
}) => {
  let point: Sample;
  await page.route("**/api/forecast?**", async (route) => {
    const response = await route.fetch();
    const forecast = await response.json();
    point = forecast.samples[Math.floor((forecast.samples.length - 1) / 2)];
    point.category = "unavailable";
    point.method = "outside";
    await route.fulfill({ json: forecast });
  });
  await page.route("**/api/observations?**", (route) =>
    route.fulfill({
      json: {
        asOf: point.at,
        mode: "replay",
        source: "Aviation Weather Center",
        items: [
          {
            id: "test-report",
            kind: "report",
            source: "AIREP",
            intensity: "unreported",
            from: point.at,
            to: null,
            baseFt: point.altitudeFt,
            topFt: point.altitudeFt,
            codes: [],
            geometry: { type: "Point", coordinates: [point.lon, point.lat] },
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await page
    .locator(".legend")
    .getByRole("button", { name: /^Unavailable ·/ })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("too little forecast data");
  await page.keyboard.press("Escape");
  await page.getByText("Map layers", { exact: true }).click();
  await page
    .getByRole("checkbox", { name: "Aircraft weather reports" })
    .check();
  await page
    .locator(".segment-weather")
    .getByRole("button", { name: /^Unreported ·/ })
    .click();
  await expect(dialog).toContainText("This observation does not say");
});

test("Edinburgh to Porto shows the recorded AIREP and Madrid warning on separate route sections", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByLabel("Weather source").selectOption("gfs-20261121-06");
  for (const [label, code] of [
    ["Departure", "EDI"],
    ["Arrival", "OPO"],
  ]) {
    await page
      .getByRole("button", { name: new RegExp(label + " airport") })
      .click();
    await page
      .getByRole("combobox", {
        name: "Search " + label.toLowerCase() + " airport",
      })
      .fill(code);
    await page.getByRole("option", { name: new RegExp(code) }).click();
  }
  await page.getByLabel("Departure time UTC").fill("14:15");
  await page.getByRole("button", { name: "Forecast flight" }).click();
  await expect(page.getByText("Edinburgh to Porto")).toBeVisible();
  await page.getByText("Map layers", { exact: true }).click();
  await page.getByRole("checkbox", { name: "Turbulence advisories" }).check();
  await page
    .getByRole("checkbox", { name: "Aircraft weather reports" })
    .check();
  await expect(page.getByText("Archived observations")).toBeVisible();
  const slider = page.getByRole("slider");
  await slider.press("Home");
  for (let i = 0; i < 18; i++) await slider.press("ArrowRight");
  const report = page
    .locator(".segment-weather li")
    .filter({ hasText: /AIREP · Light/ });
  await expect(report).toBeVisible();
  await report.getByRole("button", { name: /^Light ·/ }).click();
  await expect(page.getByRole("dialog")).toContainText("Small bumps");
  await page.keyboard.press("Escape");
  await slider.press("End");
  for (let i = Number(await slider.getAttribute("max")); i > 63; i--)
    await slider.press("ArrowLeft");
  await expect(
    page
      .locator(".segment-weather li")
      .filter({ hasText: /SIGMET LECM 3 · Severe/ }),
  ).toBeVisible();
});

test("replay observations are opt-in, dated, and stay with the selected forecast", async ({
  page,
}) => {
  const captures: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/observations")) captures.push(r.url());
  });
  await page.goto("/");
  const source = page.getByLabel("Weather source");
  await source.selectOption("gfs-20261121-06");
  await expect(page.getByRole("slider")).toBeVisible();
  expect(captures).toHaveLength(0);
  await page.getByText("Map layers", { exact: true }).click();
  await page.getByRole("checkbox", { name: "Turbulence advisories" }).check();
  await expect(page.getByText("Archived observations")).toBeVisible();
  await expect(page.getByText(/21 Nov.*18:05 UTC/)).toBeVisible();
  await page
    .getByRole("checkbox", { name: "Aircraft weather reports" })
    .check();
  await expect(
    page.getByText("Nearby observations", { exact: true }),
  ).toBeVisible();
  expect(captures).toHaveLength(1);
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes("/api/observations?run=gfs-20261123-06") && r.ok(),
    ),
    source.selectOption("gfs-20261123-06"),
  ]);
  await expect(
    page.getByRole("status").getByText(/23 Nov.*18:05 UTC/),
  ).toBeVisible();
  expect(captures.at(-1)).toContain("gfs-20261123-06");
  await page
    .getByRole("checkbox", { name: "Aircraft weather reports" })
    .uncheck();
  await page.getByRole("checkbox", { name: "Turbulence advisories" }).uncheck();
  await expect(
    page.getByText("Nearby observations", { exact: true }),
  ).toHaveCount(0);
});

test("an observation outage leaves the forecast usable", async ({ page }) => {
  await page.route("**/api/observations?**", (r) =>
    r.fulfill({
      status: 404,
      json: { message: "No weather observations for this source yet." },
    }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("slider").waitFor();
  await page.getByText("Map layers", { exact: true }).click();
  await page
    .getByRole("checkbox", { name: "Aircraft weather reports" })
    .check();
  await expect(
    page.getByText("No weather observations for this source yet."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.getByRole("slider")).toBeEnabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
