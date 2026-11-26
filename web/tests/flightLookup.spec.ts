import { expect, test } from "@playwright/test";

test("a schedule finds archived weather and uses the actual departure and arrival", async ({
  page,
}) => {
  await page.route("**/config.json", (r) =>
    r.fulfill({ json: { apiOrigin: "", flightLookup: true } }),
  );
  const day = "2026-11-24";
  await page.route("**/api/me/flight-lookup", (r) =>
    r.fulfill({
      json: {
        cached: false,
        checkedAt: 0,
        flights: [
          {
            number: "SK999",
            status: "Expected",
            aircraft: null,
            departure: {
              code: "AMS",
              name: "Schiphol",
              covered: true,
              time: { local: day + "T19:00+01:00", utc: day + "T18:00:00Z" },
            },
            arrival: {
              code: "LHR",
              name: "Heathrow",
              covered: true,
              time: { local: day + "T19:20+00:00", utc: day + "T19:20:00Z" },
            },
          },
        ],
      },
    }),
  );
  await page.goto("/forecast?demo=lookup");
  await page.getByLabel("Weather source").selectOption("gfs-20261121-06");
  await page
    .getByRole("button", { name: "Flight number", exact: true })
    .click();
  await page.getByLabel("Flight number", { exact: true }).fill("SK999");
  await page.getByLabel("Departure date (local)").fill(day);
  await page.getByRole("button", { name: "Find flight" }).click();
  await expect(page.locator(".schedule-card")).toContainText("Not listed");
  const supplier = "https://aerodatabox.com/";
  await page
    .context()
    .route(supplier, (route) =>
      route.fulfill({ contentType: "text/html", body: "Schedule provider" }),
    );
  const referral = page
    .context()
    .waitForEvent("request", (r) => r.url() === supplier);
  const providerTab = page.waitForEvent("popup");
  await page.getByRole("link", { name: "AeroDataBox" }).click();
  expect((await referral).headers().referer).toBe(
    new URL(page.url()).origin + "/",
  );
  await (await providerTab).close();
  const routed = page.waitForResponse((r) => {
    const u = new URL(r.url());
    return (
      u.pathname === "/api/forecast" &&
      u.searchParams.get("arrival") === day + "T19:20:00Z"
    );
  });
  await page.getByRole("button", { name: "View replay forecast" }).click();
  const payload = await (await routed).json();
  expect(payload.durationMinutes).toBe(80);
  expect(payload.run.runId).toBe("gfs-20261124-12");
  await expect(page.getByLabel("Weather source")).toHaveValue(
    "gfs-20261124-12",
  );
  await expect(page.locator(".route-codes")).toContainText("LHR");
  await expect(
    page.getByText(/SK999 · Estimated great-circle route/),
  ).toBeVisible();
});

test("no schedule, quota errors and airport fallback work on a small screen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 750 });
  let count = 0;
  await page.route("**/config.json", (r) =>
    r.fulfill({ json: { apiOrigin: "", flightLookup: true } }),
  );
  await page.route("**/api/me/flight-lookup", (r) =>
    ++count === 1
      ? r.fulfill({ json: { cached: false, checkedAt: 0, flights: [] } })
      : r.fulfill({
          status: 429,
          json: {
            message:
              "The flight lookup allowance has been reached. You can still search by airports.",
          },
        }),
  );
  await page.goto("/forecast");
  const edit = page.getByRole("button", { name: "Edit flight" });
  await expect(edit).toHaveAttribute("aria-expanded", "false");
  await edit.click();
  await page
    .getByRole("button", { name: "Flight number", exact: true })
    .click();
  await page.getByLabel("Flight number", { exact: true }).fill("KL1001");
  await page.getByRole("button", { name: "Find flight" }).click();
  await expect(page.getByText(/No matching flight was found/)).toBeVisible();
  await page.getByRole("button", { name: "Find flight" }).click();
  await expect(page.getByRole("alert")).toContainText("allowance");
  await page.getByRole("button", { name: "Airports", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Forecast flight" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(375);
});
