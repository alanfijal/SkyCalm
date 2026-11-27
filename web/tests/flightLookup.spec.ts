import { expect, test } from "@playwright/test";

const dayOfFlight = "2030-02-15";
const brusselsHamburg = {
  number: "XY480",
  status: "Expected",
  aircraft: "regional jet",
  departure: {
    code: "BRU",
    name: "Brussels",
    covered: true,
    time: {
      utc: dayOfFlight + "T15:40:00Z",
      local: dayOfFlight + "T16:40+01:00",
    },
  },
  arrival: {
    code: "HAM",
    name: "Hamburg",
    covered: true,
    time: {
      utc: dayOfFlight + "T17:10:00Z",
      local: dayOfFlight + "T18:10+01:00",
    },
  },
};

test("a flight after the forecast window replaces the previous map with its own schedule", async ({
  page,
  request,
}) => {
  await page.clock.setFixedTime(new Date(dayOfFlight + "T08:00:00Z"));
  const manual = await request.get("/api/forecast", {
    params: {
      origin: "BCN",
      destination: "ARN",
      departure: "2026-11-21T12:00:00Z",
      run: "gfs-20261121-06",
    },
  });
  expect(manual.ok()).toBe(true);
  const example = await manual.json();
  const latest = {
    ...example.run,
    runId: "gfs-20300214-00",
    issued: "2030-02-14T00:00:00Z",
    validUntil: dayOfFlight + "T12:00:00Z",
  };
  await page.route("**/config.json", (r) =>
    r.fulfill({ json: { apiOrigin: "", flightLookup: true } }),
  );
  await page.route("**/api/runs", (r) =>
    r.fulfill({
      json: {
        latest,
        replays: [example.run],
        serverTime: dayOfFlight + "T08:00:00Z",
      },
    }),
  );
  const weatherRequests: string[] = [];
  await page.route("**/api/forecast?**", (r) => {
    weatherRequests.push(
      new URL(r.request().url()).searchParams.get("destination")!,
    );
    return r.fulfill({ json: example });
  });
  await page.route("**/api/me/flight-lookup", (r) =>
    r.fulfill({
      json: { flights: [brusselsHamburg], cached: true, checkedAt: 0 },
    }),
  );
  await page.goto("/forecast");
  const map = page.getByRole("region", { name: "Flight map" });
  await expect(map.locator(".route-codes")).toHaveText("BCNARN");
  await page
    .getByRole("button", { name: "Flight number", exact: true })
    .click();
  await expect(map.locator(".route-codes")).toHaveCount(0);
  await page.getByLabel("Flight number", { exact: true }).fill("XY480");
  await page.getByRole("button", { name: "Find flight" }).click();
  await expect(map.locator(".route-codes")).toHaveText("BRUHAM");
  await expect(map).toContainText("Brussels to Hamburg");
  await expect(map).toContainText(
    "This forecast ends 15 Feb at 12:00 UTC. The flight departs 15 Feb at 15:40 UTC.",
  );
  await expect(
    map.getByRole("img", {
      name: "Airport locations: BRU to HAM, direct line",
    }),
  ).toBeVisible();
  await expect(page.getByLabel("Intensity legend")).toHaveCount(0);
  await expect(page.locator(".timeline")).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Save route", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Save to My flights" }),
  ).toBeVisible();
  await page.getByLabel("Weather source").selectOption(example.run.runId);
  await expect(map.locator(".route-codes")).toHaveText("BRUHAM");
  await expect(map).toContainText("15 Feb at 15:40 UTC");
  await page.getByLabel("Flight number", { exact: true }).fill("ZZ731");
  await expect(map.locator(".route-codes")).toHaveCount(0);
  expect(weatherRequests).toEqual(["ARN"]);
});

test("a late search response cannot select an old leg and multiple matches need a choice", async ({
  page,
}) => {
  await page.route("**/config.json", (r) =>
    r.fulfill({ json: { apiOrigin: "", flightLookup: true } }),
  );
  let finishFirst!: () => void;
  const held = new Promise<void>((resolve) => {
    finishFirst = resolve;
  });
  await page.route("**/api/me/flight-lookup", async (r) => {
    const first = r.request().postDataJSON().number === "XY480";
    if (first) await held;
    const outbound = { ...brusselsHamburg, number: "ZZ731" };
    const inbound = {
      ...outbound,
      departure: outbound.arrival,
      arrival: outbound.departure,
    };
    return r.fulfill({
      json: {
        cached: true,
        checkedAt: 0,
        flights: first ? [brusselsHamburg] : [outbound, inbound],
      },
    });
  });
  await page.goto("/forecast");
  await page
    .getByRole("button", { name: "Flight number", exact: true })
    .click();
  const input = page.getByLabel("Flight number", { exact: true });
  await input.fill("XY480");
  const pending = page.waitForRequest("**/api/me/flight-lookup");
  await page.getByRole("button", { name: "Find flight" }).click();
  await pending;
  await input.fill("ZZ731");
  await page.getByRole("button", { name: "Find flight" }).click();
  const map = page.getByRole("region", { name: "Flight map" });
  await expect(page.locator(".schedule-card")).toHaveCount(2);
  await expect(map.locator(".route-codes")).toHaveCount(0);
  await page
    .locator(".schedule-card")
    .nth(1)
    .getByRole("button", { name: "Show route" })
    .click();
  await expect(map.locator(".route-codes")).toHaveText("HAMBRU");
  const oldResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/me/flight-lookup") &&
      r.request().postDataJSON().number === "XY480",
  );
  finishFirst();
  await oldResponse;
  await expect(page.locator(".schedule-card")).toHaveCount(2);
  await expect(map.locator(".route-codes")).toHaveText("HAMBRU");
});

test("a single match loads weather automatically when the selected run covers its timetable", async ({
  page,
}) => {
  await page.route("**/config.json", (r) =>
    r.fulfill({ json: { apiOrigin: "", flightLookup: true } }),
  );
  const day = "2026-11-21";
  const utc = (time: string) => day + "T" + time + ":00Z";
  const departure = {
    ...brusselsHamburg.departure,
    time: { local: day + "T13:20+01:00", utc: utc("12:20") },
  };
  const arrival = {
    ...brusselsHamburg.arrival,
    time: { local: day + "T15:00+01:00", utc: utc("14:00") },
  };
  await page.route("**/api/me/flight-lookup", (r) =>
    r.fulfill({
      json: {
        flights: [{ ...brusselsHamburg, departure, arrival }],
        checkedAt: 0,
        cached: true,
      },
    }),
  );
  await page.goto("/forecast");
  await page.getByLabel("Weather source").selectOption("gfs-20261121-06");
  await page
    .getByRole("button", { name: "Flight number", exact: true })
    .click();
  await page.getByLabel("Flight number", { exact: true }).fill("XY480");
  await page.getByLabel("Departure date (local)").fill(day);
  const response = page.waitForResponse((r) => {
    const u = new URL(r.url());
    return (
      u.pathname === "/api/forecast" &&
      u.searchParams.get("destination") === "HAM"
    );
  });
  await page.getByRole("button", { name: "Find flight" }).click();
  const actual = await response;
  expect(actual.ok()).toBe(true);
  const params = new URL(actual.url()).searchParams;
  expect([
    params.get("origin"),
    params.get("departure"),
    params.get("arrival"),
  ]).toEqual(["BRU", utc("12:20"), utc("14:00")]);
  const map = page.getByRole("region", { name: "Flight map" });
  await expect(map.locator(".route-codes")).toHaveText("BRUHAM");
  await expect(map.getByLabel("Intensity legend")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "View replay forecast" }),
  ).toHaveCount(0);
});

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
