import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("the public replay plays, pauses, scrubs and restarts at the recorded airports", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Replay a recorded flight" }).click();
  await expect(page).toHaveURL(/\/replay$/);
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
  await page.getByLabel("Flight number", { exact: true }).fill("AZ1704");
  await page.getByLabel("Departure date (local)").fill(day);
  await page.getByRole("button", { name: "Find flight" }).click();
  const links = page.getByRole("link", { name: "Replay this recorded flight" });
  await expect(links).toHaveCount(1);
  await links.click();
  await expect(
    page.getByRole("heading", { name: "Catania to Milan Linate" }),
  ).toBeVisible();
});
