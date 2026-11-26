import { expect, test, type Page } from "@playwright/test";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
const login = "https://login.skycalm.test",
  issuer = "https://identity.skycalm.test/pool",
  clientId = "classroom-web";
const base = "http://127.0.0.1:4187";
const headers = {
  "access-control-allow-origin": base,
  "access-control-allow-headers": "*",
  "access-control-allow-methods": "GET,POST,PUT,DELETE,OPTIONS",
};
const encode = (v: unknown) =>
  Buffer.from(JSON.stringify(v)).toString("base64url");

async function provider(
  page: Page,
  result:
    "success" | "wrong-state" | "invite-denied" | "provider-error" = "success",
  presenter = false,
  flightLookup = false,
) {
  const { privateKey, publicKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
  });
  const user = "10c81a04-cd46-4c33-9af2-26f059de08e3";
  let nonce = "",
    challenge = "",
    tokenRequests = 0;
  await page.route("**/config.json", (r) =>
    r.fulfill({
      json: {
        apiOrigin: "",
        flightLookup,
        auth: { domain: login, issuer, clientId, vapidPublicKey: "" },
      },
    }),
  );
  await page.route(login + "/oauth2/authorize?**", async (r) => {
    const params = new URL(r.request().url()).searchParams;
    expect(params.get("response_type")).toBe("code");
    expect(params.get("code_challenge_method")).toBe("S256");
    nonce = params.get("nonce")!;
    challenge = params.get("code_challenge")!;
    const reply = new URL(base);
    reply.searchParams.set(
      "state",
      result === "wrong-state" ? "incorrect" : params.get("state")!,
    );
    if (result === "invite-denied" || result === "provider-error") {
      reply.searchParams.set("error", "server_error");
      reply.searchParams.set(
        "error_description",
        result === "invite-denied"
          ? "PreSignUp failed with error This classroom is invitation only."
          : "Internal provider diagnostic",
      );
    } else {
      reply.searchParams.set("code", "classroom");
    }
    await r.fulfill({
      status: 302,
      headers: { location: reply.href },
    });
  });
  await page.route(login + "/oauth2/token", async (r) => {
    if (r.request().method() === "OPTIONS")
      return r.fulfill({ status: 204, headers });
    tokenRequests++;
    const verifier = new URLSearchParams(r.request().postData() ?? "").get(
      "code_verifier",
    )!;
    expect(createHash("sha256").update(verifier).digest("base64url")).toBe(
      challenge,
    );
    const iat = Math.floor(Date.now() / 1000);
    const unsigned =
      encode({ alg: "RS256", kid: "demo-1" }) +
      "." +
      encode({
        iss: issuer,
        aud: clientId,
        sub: user,
        nonce,
        iat,
        exp: iat + 900,
        token_use: "id",
        "cognito:groups": presenter ? ["admins"] : [],
      });
    const signature = sign(
      "RSA-SHA256",
      Buffer.from(unsigned),
      privateKey,
    ).toString("base64url");
    await r.fulfill({
      headers,
      json: {
        access_token: "demo-access",
        refresh_token: "demo-refresh",
        id_token: unsigned + "." + signature,
        token_type: "Bearer",
        expires_in: 900,
      },
    });
  });
  await page.route(issuer + "/.well-known/jwks.json", (r) =>
    r.fulfill({
      headers,
      json: {
        keys: [
          {
            ...publicKey.export({ format: "jwk" }),
            kid: "demo-1",
            alg: "RS256",
            use: "sig",
          },
        ],
      },
    }),
  );
  return () => tokenRequests;
}

test("a passenger signs in, saves a flight, exports and deletes the account", async ({
  page,
}) => {
  const exchanges = await provider(page);
  let flight: Record<string, unknown> | undefined,
    deleted = false;
  await page.route("**/api/me**", async (r) => {
    expect(r.request().headers()["authorization"]).toBe("Bearer demo-access");
    const path = new URL(r.request().url()).pathname;
    if (r.request().method() === "PUT") {
      flight = {
        ...r.request().postDataJSON(),
        slot: 1,
        id: "flight-1",
        watch: "live",
      };
      return r.fulfill({ json: flight });
    }
    if (r.request().method() === "DELETE") {
      expect(r.request().postDataJSON().confirm).toBe("DELETE");
      deleted = true;
      return r.fulfill({ json: { deleted: true } });
    }
    if (path.endsWith("export"))
      return r.fulfill({ json: { flights: flight ? [flight] : [] } });
    return r.fulfill({
      json: {
        flights: flight ? [flight] : [],
        inbox: [],
        preferences: { push: false, email: false },
      },
    });
  });
  await page.route(login + "/logout?**", (r) =>
    r.fulfill({ status: 302, headers: { location: base + "/" } }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/flights");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Add flight" }).click();
  expect(exchanges()).toBe(1);
  await page.getByLabel("Departure airport code").fill("BCN");
  await page.getByLabel("Arrival airport code").fill("ARN");
  await page.getByRole("button", { name: "Save flight" }).click();
  await expect(page.getByRole("heading", { name: "BCN ARN" })).toBeVisible();
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    ),
  ).not.toContain("demo-access");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.getByRole("button", { name: "Account", exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export my data" }).click();
  expect((await download).suggestedFilename()).toBe("skycalm-account.json");
  await page
    .getByRole("button", { name: "Delete account", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Permanently delete", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Type DELETE", { exact: false }).fill("DELETE");
  await page
    .getByRole("button", { name: "Permanently delete", exact: true })
    .click();
  await expect(page).toHaveURL(base + "/");
  expect(deleted).toBe(true);
});
test("a mismatched OAuth state is rejected before exchanging a code", async ({
  page,
}) => {
  const exchanges = await provider(page, "wrong-state");
  await page.goto("/flights");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  expect(exchanges()).toBe(0);
});
for (const [result, message] of [
  [
    "invite-denied",
    "Sign in with the email address on your classroom invitation.",
  ],
  ["provider-error", "SkyCalm couldn’t complete sign-in. Please try again."],
] as const) {
  test(`a ${result} callback explains how to retry`, async ({ page }) => {
    const exchanges = await provider(page, result);
    await page.goto("/flights");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("alert")).toHaveText(message);
    await expect(page).toHaveURL(base + "/flights");
    expect(exchanges()).toBe(0);
  });
}
test("a presenter can compare signed-out, passenger and presenter access", async ({
  page,
}) => {
  let presenterScope = false;
  await provider(page, "success", true);
  await page.route("**/api/me", (r) =>
    r.fulfill({
      json: {
        flights: [],
        inbox: [],
        preferences: { push: false, email: false },
      },
    }),
  );
  await page.route("**/api/admin/health", (r) =>
    r.fulfill({
      status: r.request().headers().authorization
        ? presenterScope
          ? 200
          : 403
        : 401,
      json: { queues: {}, latestRun: null, modelVersion: null },
    }),
  );
  await page.goto("/flights");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Account", exact: true }).click();
  await page.getByRole("link", { name: "Open demo controls" }).click();
  await page.getByRole("button", { name: "Check presenter access" }).click();
  await expect(
    page.getByText("Signed out · HTTP 401. This session · HTTP 403."),
  ).toBeVisible();
  presenterScope = true;
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "System health" }).click();
  await page.getByRole("button", { name: "Check presenter access" }).click();
  await expect(
    page.getByText("Signed out · HTTP 401. This session · HTTP 200."),
  ).toBeVisible();
});

test("an anonymous visitor cannot operate the demo", async ({ page }) => {
  await provider(page);
  await page.goto("/demo");
  await expect(
    page.getByRole("heading", { name: "Operator access" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Publish replay" }),
  ).toHaveCount(0);
});

test("flight search resumes after sign-in and saves the selected timetable", async ({
  page,
}) => {
  await provider(page, "success", false, true);
  const day = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
  const dep = day + "T06:20:00Z",
    arr = day + "T07:40:00Z";
  let searches = 0,
    saved: Record<string, unknown> | undefined;
  await page.route("**/api/me**", async (r) => {
    const req = r.request();
    const path = new URL(req.url()).pathname;
    expect(req.headers().authorization).toBe("Bearer demo-access");
    if (path.endsWith("/flight-lookup")) {
      searches++;
      expect(req.postDataJSON()).toEqual({ number: "KL1001", date: day });
      return r.fulfill({
        json: {
          checkedAt: Date.now() / 1000,
          cached: false,
          flights: [
            {
              number: "KL1001",
              status: "Expected",
              aircraft: "Embraer 195",
              departure: {
                code: "AMS",
                name: "Schiphol",
                covered: true,
                time: { local: day + "T07:20+01:00", utc: dep },
              },
              arrival: {
                code: "LHR",
                name: "Heathrow",
                covered: true,
                time: { local: day + "T07:40+00:00", utc: arr },
              },
            },
          ],
        },
      });
    }
    if (req.method() === "PUT") {
      saved = {
        ...req.postDataJSON(),
        slot: 1,
        id: "saved-number",
        watch: "live",
        arrival: arr,
        arrivalScheduled: true,
      };
      return r.fulfill({ json: saved });
    }
    return r.fulfill({
      json: {
        flights: saved ? [saved] : [],
        inbox: [],
        preferences: { push: false, email: false },
      },
    });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Flight number", exact: true })
    .click();
  await page.getByLabel("Flight number", { exact: true }).fill("KL1001");
  await page.getByLabel("Departure date (local)", { exact: true }).fill(day);
  await page.getByRole("button", { name: "Find flight" }).click();
  const card = page.locator(".schedule-card");
  await expect(card).toContainText("Embraer 195");
  await expect(card).toContainText("07:20 local");
  await expect(card).toContainText("06:20 UTC");
  await expect(card).toContainText("No weather grid");
  expect(searches).toBe(1);
  await card.getByRole("link", { name: "Save to My flights" }).click();
  await expect(page.getByLabel("Departure airport code")).toHaveValue("AMS");
  await page.getByRole("button", { name: "Save flight", exact: true }).click();
  await expect(
    page.locator("article").filter({ hasText: "KL1001" }),
  ).toContainText("LHR");
  expect(saved?.flightNumber).toBe("KL1001");
  expect(saved?.scheduledArrival).toBe(arr);
  expect(new Date(String(saved?.departure)).toISOString()).toBe(
    new Date(dep).toISOString(),
  );
});
