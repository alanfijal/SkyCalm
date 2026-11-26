import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("the public replay plays, pauses, scrubs and restarts at the recorded airports", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Search recorded flights" }).click();
  await page.getByRole("searchbox").fill("Catania to Milan");
  await page.getByRole("link", { name: /AZ1704.*Play recording/ }).click();
  await expect(page).toHaveURL(/\/replay\?flight=az1704-20261121$/);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Catania to Milan Linate" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Fit route to map" }),
  ).toBeEnabled();
  const timeline = page.getByRole("slider", { name: "Point along the route" });
  await expect(timeline).toHaveValue("0");
  await expect(page.locator("time")).toHaveText("14:54 UTC");
  const csv = await page
    .getByRole("link", { name: /Download recorded positions/ })
    .getAttribute("href");
  const data = await page.request.get(csv!);
  expect((await data.text()).trim().split("\n")).toHaveLength(751);
  await page.getByRole("button", { name: "Play replay" }).click();
  await expect(timeline).not.toHaveValue("0");
  await page.getByRole("button", { name: "Pause replay" }).click();
  await expect(page.getByRole("button", { name: "Play replay" })).toBeVisible();
  await timeline.fill("70");
  await expect(page.locator(".recording-controls time")).toHaveText(
    "16:04 UTC",
  );
  await page.getByRole("button", { name: /^LIN ·/ }).click();
  await expect(timeline).toHaveValue("110");
  await expect(page.locator("time")).toHaveText("16:43 UTC");
  await expect(page.locator(".recording-controls")).toContainText("400 ft");
  await page.getByRole("button", { name: "Play again" }).click();
  await expect(
    page.getByRole("button", { name: "Pause replay" }),
  ).toBeVisible();
  await timeline.fill("9");
  await expect(page.getByRole("button", { name: "Play replay" })).toBeVisible();
  await page.setViewportSize({ width: 360, height: 800 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - innerWidth,
    ),
  ).toBe(0);
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
  await page.getByRole("link", { name: "Flight forecast" }).click();
  await expect(page.getByLabel("Weather source")).toBeVisible();
});

test("a missing recording can be retried without an account or schedule call", async ({
  page,
}) => {
  let available = false;
  const apiCalls: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/")) apiCalls.push(r.url());
  });
  await page.route("**/data/recorded-flight/*.json", (r) =>
    available ? r.continue() : r.fulfill({ status: 404 }),
  );
  await page.goto("/replay");
  await expect(page.getByRole("alert")).toContainText("Recording unavailable");
  available = true;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("slider")).toHaveValue("0");
  expect(apiCalls).toEqual([]);
});

test("only the matching schedule leg and date link to the archive", async ({
  page,
}) => {
  const day = "2026-11-21";
  await page.route("**/config.json", (r) =>
    r.fulfill({ json: { apiOrigin: "", flightLookup: true } }),
  );
  await page.route("**/api/me/flight-lookup", (r) => {
    const leg = {
      number: "AZ 1704",
      status: "Arrived",
      aircraft: "Airbus A220",
      departure: {
        code: "CTA",
        name: "Catania",
        covered: true,
        time: { local: day + "T15:50+01:00", utc: day + "T14:50Z" },
      },
      arrival: {
        code: "LIN",
        name: "Milan Linate",
        covered: true,
        time: { local: day + "T17:50+01:00", utc: day + "T16:50Z" },
      },
    };
    return r.fulfill({
      json: {
        flights: [
          leg,
          { ...leg, arrival: { ...leg.arrival, code: "MXP" } },
          {
            ...leg,
            departure: {
              ...leg.departure,
              time: {
                local: "2026-11-22T15:50+01:00",
                utc: "2026-11-22T14:50Z",
              },
            },
          },
        ],
        cached: true,
        checkedAt: 0,
      },
    });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Flight number", exact: true })
    .click();
  // A schedule search can return an operating flight under a different number.
  await page.getByLabel("Flight number", { exact: true }).fill("XX123");
  await page.getByLabel("Departure date (local)").fill(day);
  await page.getByRole("button", { name: "Find flight" }).click();
  const links = page.getByRole("link", { name: "Replay this recorded flight" });
  await expect(links).toHaveCount(1);
  await links.click();
  await expect(
    page.getByRole("heading", { name: "Catania to Milan Linate" }),
  ).toBeVisible();
});

test("search by flight number or callsign opens the dated recording while signed out", async ({
  page,
}) => {
  let calls = 0;
  await page.route("**/config.json", (r) =>
    r.fulfill({
      json: {
        apiOrigin: "",
        flightLookup: true,
        auth: { domain: "https://unused.invalid", clientId: "unused" },
      },
    }),
  );
  await page.route("**/api/me/flight-lookup", (r) => {
    calls++;
    return r.fulfill({ status: 503 });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Flight number", exact: true })
    .click();
  await page.getByLabel("Flight number", { exact: true }).fill("KLM71Z");
  await page.getByLabel("Departure date (local)").fill("2026-11-21");
  await page.getByRole("button", { name: "Find flight" }).click();
  await page.getByRole("link", { name: /KL1521.*Play recording/ }).click();
  await expect(
    page.getByRole("heading", { name: "Amsterdam to Barcelona" }),
  ).toBeVisible();
  await expect(page.locator("time")).toHaveText("19:58 UTC");
  await expect(
    page.getByRole("link", { name: /Download recorded positions/ }),
  ).toHaveAttribute("href", /kl1521-20261121\.csv$/);
  expect(calls).toBe(0);
});

test("search remembers the flight direction and date on mobile and handles unknown recordings", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto("/recordings?q=Manchester");
  const results = page.locator(".recording-results a");
  await expect(results).toHaveCount(2);
  await page.getByRole("searchbox").fill("TRN to MAN");
  await page.getByLabel("Departure date (optional)").fill("2026-11-22");
  await expect(page.getByRole("status")).toHaveText(
    "No recorded flights match these filters.",
  );
  await page.getByLabel("Departure date (optional)").fill("2026-11-21");
  await expect(results).toHaveCount(1);
  await expect(results).toContainText("FR1801");
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - innerWidth,
    ),
  ).toBe(0);
  await results.click();
  await expect(
    page.getByRole("heading", { name: "Turin to Manchester" }),
  ).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("searchbox")).toHaveValue("TRN to MAN");
  await expect(results).toHaveCount(1);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(results).toHaveCount(6);
  await page.goto("/replay?flight=unknown");
  await expect(
    page.getByRole("heading", { name: "Recording not found" }),
  ).toBeVisible();
});

test("airport selection surfaces archived flights and a weather forecast route can play independently", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Weather source").selectOption("gfs-20261121-06");
  const playback = page.getByRole("button", { name: "Play forecast route" });
  await expect(playback).toBeVisible();
  const timeline = page.getByRole("slider", { name: "Point along the route" });
  await timeline.fill("0");
  await playback.click();
  await expect(timeline).not.toHaveValue("0", { timeout: 8000 });
  await timeline.press("Home");
  await expect(timeline).toHaveValue("0");
  await expect(playback).toBeVisible();
  for (const [field, code] of [
    ["departure", "AMS"],
    ["arrival", "DUB"],
  ]) {
    await page
      .getByRole("button", { name: new RegExp(field + " airport", "i") })
      .click();
    await page
      .getByRole("combobox", { name: "Search " + field + " airport" })
      .fill(code);
    await page
      .getByRole("option", { name: new RegExp(code) })
      .first()
      .click();
  }
  const matches = page.getByRole("region", {
    name: "Recorded flights on this route",
  });
  await expect(matches.getByRole("link")).toContainText("KL1139");
  await page.getByRole("button", { name: "Swap airports" }).click();
  await expect(matches).toHaveCount(0);
});
