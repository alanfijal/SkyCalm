import * as oauth from "oauth4webapi";

export interface Settings {
  apiOrigin: string;
  flightLookup?: boolean;
  auth?: {
    domain: string;
    issuer: string;
    clientId: string;
  };
}
type Auth = NonNullable<Settings["auth"]>;
const transaction = "skycalm-login";
let session:
  | {
      access: string;
      refresh?: string;
      until: number;
      admin: boolean;
      operator: boolean;
      method: string;
    }
  | undefined;
let refreshing: Promise<string> | undefined;
let settings: Promise<Settings> | undefined;

export const config = () =>
  (settings ??= fetch("/config.json", { cache: "no-store" })
    .then((r) => {
      if (!r.ok) throw Error("Could not load sign-in settings.");
      return r.json() as Promise<Settings>;
    })
    .catch((e) => {
      settings = undefined;
      throw e;
    }));
const callback = () => location.origin + "/";
function server(a: Auth): oauth.AuthorizationServer {
  return {
    issuer: a.issuer,
    authorization_endpoint: a.domain + "/oauth2/authorize",
    token_endpoint: a.domain + "/oauth2/token",
    jwks_uri: a.issuer + "/.well-known/jwks.json",
  };
}
export const canOperate = () => Boolean(session?.admin && session.operator);
export const signedIn = () => Boolean(session);
export const signInMethod = () => session?.method ?? "SkyCalm sign-in";
export const isAdmin = () => Boolean(session?.admin);
export async function signIn(a: Auth, path: string) {
  const verifier = oauth.generateRandomCodeVerifier(),
    state = oauth.generateRandomState(),
    nonce = oauth.generateRandomNonce();
  const safePath = ["/", "/forecast", "/demo", "/health"].includes(path)
    ? path
    : "/flights";
  const scopes = [
    "openid",
    "email",
    "aws.cognito.signin.user.admin",
    "skycalm/flights.read",
    "skycalm/flights.write",
    "skycalm/notifications.write",
  ];
  if (safePath === "/demo" || safePath === "/health")
    scopes.push("skycalm/admin");
  const params = new URLSearchParams({
    client_id: a.clientId,
    response_type: "code",
    redirect_uri: callback(),
    scope: scopes.join(" "),
    state,
    nonce,
    code_challenge: await oauth.calculatePKCECodeChallenge(verifier),
    code_challenge_method: "S256",
  });
  sessionStorage.setItem(
    transaction,
    JSON.stringify({
      verifier,
      state,
      nonce,
      path: safePath,
      inbox:
        safePath === "/flights" &&
        new URLSearchParams(location.search).get("view") === "inbox",
      flight:
        safePath === "/flights"
          ? new URLSearchParams(location.search).get("flight")
          : null,
      started: Date.now(),
    }),
  );
  location.assign(a.domain + "/oauth2/authorize?" + params);
}

export async function finishSignIn(a: Auth, url: URL) {
  const record = sessionStorage.getItem(transaction);
  sessionStorage.removeItem(transaction);
  history.replaceState(null, "", "/flights");
  if (!record)
    throw Error("This sign-in link has expired. Please sign in again.");
  const tx = JSON.parse(record);
  if (
    !Number.isFinite(tx.started) ||
    Math.abs(Date.now() - tx.started) > 600000
  )
    throw Error("Sign-in expired. Try again.");
  const as = server(a),
    client = { client_id: a.clientId, id_token_signed_response_alg: "RS256" };
  let checked: URLSearchParams;
  try {
    checked = oauth.validateAuthResponse(as, client, url, tx.state);
  } catch (error) {
    if (!(error instanceof oauth.AuthorizationResponseError)) throw error;
    if (
      error.error_description?.includes("This classroom is invitation only")
    ) {
      throw Error(
        "Sign in with the email address on your classroom invitation.",
        { cause: error },
      );
    }
    if (error.error === "access_denied") {
      throw Error(
        "Sign-in was cancelled or declined. Choose Sign in to try again.",
        { cause: error },
      );
    }
    throw Error("SkyCalm couldn’t complete sign-in. Please try again.", {
      cause: error,
    });
  }
  const raw = await oauth.authorizationCodeGrantRequest(
    as,
    client,
    oauth.None(),
    checked,
    callback(),
    tx.verifier,
  );
  const result = await oauth.processAuthorizationCodeResponse(as, client, raw, {
    expectedNonce: tx.nonce,
    requireIdToken: true,
  });
  await oauth.validateApplicationLevelSignature(as, raw);
  const id = oauth.getValidatedIdTokenClaims(result);
  const groups = id?.["cognito:groups"];
  session = {
    method:
      (Array.isArray(id?.identities) &&
        id.identities.some(
          (x) =>
            typeof x === "object" &&
            x !== null &&
            "providerName" in x &&
            x.providerName === "Google",
        )) ||
      String(id?.["cognito:username"] ?? "").startsWith("Google_")
        ? "Google"
        : "Amazon Cognito",
    access: result.access_token,
    refresh: result.refresh_token,
    until: Date.now() + Number(result.expires_in ?? 900) * 1000,
    admin: Array.isArray(groups) && groups.includes("admins"),
    operator: tx.path === "/demo" || tx.path === "/health",
  };
  return ["/", "/forecast", "/demo", "/health"].includes(tx.path)
    ? tx.path === "/"
      ? "/forecast"
      : tx.path
    : typeof tx.flight === "string" && /^[0-9a-f-]{36}$/.test(tx.flight)
      ? "/flights?flight=" + encodeURIComponent(tx.flight)
      : tx.inbox
        ? "/flights?view=inbox"
        : "/flights";
}

async function accessToken(a: Auth): Promise<string> {
  if (!session) throw Error("Please sign in to continue.");
  if (session.until > Date.now() + 30000) return session.access;
  if (refreshing) return refreshing;
  if (!session.refresh) {
    session = undefined;
    throw Error("Your session expired. Sign in again.");
  }
  const previous = session;
  refreshing = (async () => {
    try {
      const as = server(a),
        client = { client_id: a.clientId };
      const response = await oauth.refreshTokenGrantRequest(
        as,
        client,
        oauth.None(),
        previous.refresh!,
      );
      const next = await oauth.processRefreshTokenResponse(
        as,
        client,
        response,
      );
      if (previous !== session) throw Error("Signed out.");
      session = {
        ...previous,
        access: next.access_token,
        refresh: next.refresh_token ?? previous.refresh,
        until: Date.now() + Number(next.expires_in ?? 900) * 1000,
      };
      return session.access;
    } catch {
      if (previous === session) session = undefined;
      throw Error("Your session expired. Sign in again.");
    } finally {
      refreshing = undefined;
    }
  })();
  return refreshing;
}

export async function privateApi<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const c = await config();
  if (!c.auth) throw Error("Sign-in is unavailable in this environment.");
  const token = await accessToken(c.auth);
  const r = await fetch(c.apiOrigin + path, {
    method,
    cache: "no-store",
    referrerPolicy: "no-referrer",
    headers: {
      authorization: "Bearer " + token,
      ...(body === undefined ? {} : { "content-type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  });
  if (!r.ok) {
    if (r.status === 401) session = undefined;
    const info = await r.json().catch(() => ({}));
    throw Error(
      info.message ?? "Could not complete the request. Please try again.",
    );
  }
  return r.json();
}
export async function presenterAccessStatus() {
  const settings = await config();
  if (!settings.auth) throw Error("Sign in is unavailable.");
  const token = await accessToken(settings.auth);
  const url = settings.apiOrigin + "/api/admin/health";
  async function status(headers: HeadersInit) {
    const response = await fetch(url, {
      method: "GET",
      headers,
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
      signal: AbortSignal.timeout(15000),
    });
    await response.body?.cancel();
    return response.status;
  }
  const [anonymous, current] = await Promise.all([
    status({}),
    status({ authorization: "Bearer " + token }),
  ]);
  return { anonymous, current };
}

export function signOut(a: Auth) {
  session = undefined;
  sessionStorage.removeItem(transaction);
  location.assign(
    a.domain +
      "/logout?" +
      new URLSearchParams({ client_id: a.clientId, logout_uri: callback() }),
  );
}
