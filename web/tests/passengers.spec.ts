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

async function provider(page: Page, wrongState = false) {
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
    await r.fulfill({
      status: 302,
      headers: {
        location:
          base +
          "/?code=classroom&state=" +
          (wrongState ? "incorrect" : params.get("state")),
      },
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
  const exchanges = await provider(page, true);
  await page.goto("/flights");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  expect(exchanges()).toBe(0);
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
