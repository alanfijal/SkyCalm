import { Skeleton } from "./PageSkeleton";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  Download,
  Plane,
  Plus,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import {
  canOperate,
  signInMethod,
  config,
  isAdmin,
  presenterAccessStatus,
  privateApi,
  signedIn,
  signIn,
  signOut,
  type Settings,
} from "./passengerAuth";
import { dateLabel, clock } from "./types";
import { FlightSummary, Journey } from "./FlightJourney";
import JourneyForm from "./JourneyForm";
import {
  NoticeCentre,
  PastCard,
  SetupChecklist,
  TravelPreferences,
} from "./PassengerSettings";
import {
  flightHref,
  type Flight,
  type Notice,
  type Preferences,
} from "./journey";
import "./passengers.css";
import { clearDraft, draft, type FlightForm } from "./flightDraft";

interface Overview {
  closing?: boolean;
  flights: Flight[];
  inbox: Notice[];
  preferences: Preferences;
}
const time = (d: string) => dateLabel(d) + " · " + clock(d) + " UTC";
const endpoint = "/api/me";
function PresenterAccessCheck() {
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  async function check() {
    setBusy(true);
    try {
      const { anonymous, current } = await presenterAccessStatus();
      setResult(
        `Signed out · HTTP ${anonymous}. This session · HTTP ${current}.`,
      );
    } catch {
      setResult("The access check could not reach the service.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button disabled={busy} onClick={check}>
        Check presenter access
      </button>
      <p role="status">{result}</p>
    </div>
  );
}
const freshForm = (): FlightForm => ({
  origin: "",
  destination: "",
  departure: new Date(Date.now() + 24 * 3600000).toISOString().slice(0, 16),
});
export default function Passengers({
  path,
  initialError,
}: {
  path: string;
  initialError: string;
}) {
  const [settings, setSettings] = useState<Settings>(),
    [data, setData] = useState<Overview>();
  const [error, setError] = useState(initialError),
    [busy, setBusy] = useState(false),
    [tab, setTab] = useState(
      new URLSearchParams(location.search).get("view") === "inbox"
        ? "inbox"
        : "flights",
    );
  const [form, setForm] = useState(() => draft() ?? freshForm()),
    [edit, setEdit] = useState<Flight | null | undefined>(() =>
      draft() ? null : undefined,
    );
  const [deleting, setDeleting] = useState(false),
    [confirm, setConfirm] = useState(""),
    [message, setMessage] = useState("");
  const admin = path !== "/flights";
  const requested = new URLSearchParams(location.search).get("flight");
  const selected = data?.flights.find((f) => f.id === requested);
  const [past, setPast] = useState(false);
  const [endSessions, setEndSessions] = useState(false);
  function add() {
    setForm({ ...freshForm(), origin: data?.preferences.homeAirport ?? "" });
    setEdit(null);
    setPast(false);
    setTab("flights");
  }
  const now = Date.now();
  const listed = (data?.flights ?? [])
    .filter((f) => Date.parse(f.arrival) <= now === past)
    .sort(
      (a, b) =>
        (past ? -1 : 1) * (Date.parse(a.departure) - Date.parse(b.departure)),
    );
  const refresh = useCallback(
    async () => setData(await privateApi<Overview>(endpoint)),
    [],
  );
  useEffect(() => {
    let live = true;
    config()
      .then(async (c) => {
        if (!live) return;
        setSettings(c);
        if (c.auth && signedIn()) await refresh();
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [refresh]);
  useEffect(() => {
    if (!data || !signedIn()) return;
    const id = setInterval(() => {
      if (document.visibilityState === "visible") refresh().catch(() => {});
    }, 30000);
    return () => clearInterval(id);
  }, [Boolean(data), refresh]);
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }
  async function save(next: FlightForm) {
    const slot =
      edit?.slot ??
      Array.from({ length: 8 }, (_, i) => i + 1).find(
        (s) => !data?.flights.some((f) => f.slot === s),
      );
    if (!slot) throw Error("You can save eight flights.");
    await privateApi(endpoint + "/flights/" + slot, "PUT", {
      ...next,
      departure: new Date(next.departure + "Z").toISOString(),
      revision: crypto.randomUUID(),
      previous: edit?.revision,
    });
    setEdit(undefined);
    await refresh();
    clearDraft();
    setMessage("Flight saved.");
  }
  async function push() {
    if (
      !("serviceWorker" in navigator) ||
      !("PushManager" in window) ||
      !("Notification" in window)
    )
      throw Error(
        "On iPhone, add SkyCalm to your Home Screen and open it there to enable notifications.",
      );

    if (!data?.preferences.push) {
      const permission = await Notification.requestPermission();
      if (permission !== "granted")
        throw Error("Notifications are disabled in your browser settings.");
    }
    const reg = await Promise.race([
      navigator.serviceWorker.ready,
      new Promise<never>((_, reject) =>
        setTimeout(
          () =>
            reject(
              Error(
                "The browser notification service is unavailable. Reopen SkyCalm and try again.",
              ),
            ),
          10000,
        ),
      ),
    ]);
    let sub = await reg.pushManager.getSubscription();
    if (data?.preferences.push) {
      await privateApi(endpoint + "/preferences", "PUT", {
        channel: "push",
        subscription: null,
      });
      await sub?.unsubscribe();
    } else {
      const k = settings?.auth?.vapidPublicKey;
      if (!k) throw Error("Browser delivery has not been configured.");
      sub ??= await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: Uint8Array.from(
          atob(k.replace(/-/g, "+").replace(/_/g, "/")),
          (c) => c.charCodeAt(0),
        ),
      });
      await privateApi(endpoint + "/preferences", "PUT", {
        channel: "push",
        subscription: sub.toJSON(),
      });
    }
    await refresh();
  }
  async function download() {
    const data = await privateApi(endpoint + "/export");
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "skycalm-account.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <main className="passenger-page">
      <header className="pass-nav">
        <a href="/" className="brand">
          <img src="/skycalm.svg" width="32" height="32" alt="" />
          SkyCalm
        </a>
        <a href="/forecast">
          <ArrowLeft size={16} /> Forecast
        </a>
      </header>
      <div className="pass-shell">
        <h1>
          {admin
            ? path === "/health"
              ? "System health"
              : "Demo controls"
            : "My flights"}
        </h1>
        {error && (
          <p className="pass-error" role="alert">
            {error}
          </p>
        )}
        {message && <p role="status">{message}</p>}
        {!settings ? (
          <Skeleton label="Loading…" />
        ) : !settings.auth ? (
          <p>Passenger sign-in is unavailable in this environment.</p>
        ) : !signedIn() || (admin && !canOperate()) ? (
          <section className="pass-card">
            <ShieldCheck />
            <h2>{admin ? "Operator access" : "Your flight updates"}</h2>
            <p>
              {admin
                ? "Sign in with an administrator account to open this page."
                : "Save a route and get updates before departure."}
            </p>
            {admin && signedIn() && !isAdmin() ? (
              <p>This account has no operator access.</p>
            ) : (
              <button
                disabled={busy}
                className="pass-primary"
                onClick={() => action(() => signIn(settings.auth!, path))}
              >
                Sign in
              </button>
            )}
            {admin && signedIn() && isAdmin() && <PresenterAccessCheck />}
          </section>
        ) : data?.closing ? (
          <section className="pass-card">
            <h2>Account deletion in progress</h2>
            <p>Finish removing your sign-in after your data has been erased.</p>
            <button
              disabled={busy}
              onClick={() =>
                action(async () => {
                  await privateApi(endpoint, "DELETE", { confirm: "DELETE" });
                  signOut(settings.auth!);
                })
              }
            >
              Finish deleting account
            </button>
          </section>
        ) : admin ? (
          <Operator
            path={path}
            flights={data?.flights ?? []}
            reload={refresh}
          />
        ) : data && requested ? (
          selected ? (
            <Journey
              flight={selected}
              prefs={data.preferences}
              notices={data.inbox.filter((n) => n.flightId === selected.id)}
            />
          ) : (
            <section className="pass-card">
              <p>This saved flight is unavailable.</p>
              <a href="/flights">Back to saved flights</a>
            </section>
          )
        ) : data ? (
          <>
            <nav className="pass-tabs" aria-label="Passenger sections">
              {["flights", "inbox", "account"].map((t) => (
                <button
                  key={t}
                  aria-current={t === tab ? "page" : undefined}
                  onClick={() => {
                    setTab(t);
                    setError("");
                    setMessage("");
                  }}
                >
                  {t === "flights"
                    ? "Saved flights"
                    : t === "inbox"
                      ? "Notifications"
                      : "Account"}
                  {t === "inbox" && data.inbox.some((n) => !n.isRead)
                    ? " (" + data.inbox.filter((n) => !n.isRead).length + ")"
                    : ""}
                </button>
              ))}
            </nav>
            {tab === "flights" && (
              <>
                <SetupChecklist
                  hasFlight={!!data.flights.length}
                  notifications={
                    data.preferences.push || data.preferences.email
                  }
                  add={add}
                  account={() => setTab("account")}
                />
                <div className="pass-row">
                  <h2>{past ? "Past flights" : "Upcoming flights"}</h2>
                  {edit === undefined && (
                    <button
                      className="pass-primary"
                      disabled={data.flights.length >= 8}
                      onClick={add}
                    >
                      <Plus size={16} />
                      Add flight
                    </button>
                  )}
                </div>
                <div className="pass-actions">
                  <button
                    aria-pressed={!past}
                    onClick={() => {
                      setPast(false);
                      setEdit(undefined);
                    }}
                  >
                    Upcoming
                  </button>
                  <button
                    aria-pressed={past}
                    onClick={() => {
                      setPast(true);
                      setEdit(undefined);
                    }}
                  >
                    Past
                  </button>
                </div>
                {edit !== undefined && (
                  <JourneyForm
                    key={edit?.revision ?? "new"}
                    initial={form}
                    edit={Boolean(edit)}
                    busy={busy}
                    schedules={Boolean(settings.flightLookup)}
                    onCancel={() => setEdit(undefined)}
                    onSave={(next) => void action(() => save(next))}
                  />
                )}
                {!listed.length && edit === undefined && (
                  <section className="pass-card">
                    <Plane />
                    <h3>{past ? "No past flights" : "No upcoming flights"}</h3>
                    <p>
                      {past
                        ? "After arrival, your recap stays here for seven days."
                        : "Save a flight to follow its forecast."}
                    </p>
                  </section>
                )}
                {listed.map((f) => (
                  <article className="pass-card pass-route" key={f.id}>
                    <div>
                      <FlightSummary
                        flight={f}
                        prefs={data.preferences}
                        now={now}
                      />
                      {past && <PastCard f={f} prefs={data.preferences} />}
                    </div>
                    <div className="pass-actions">
                      <a href={flightHref(f.id)}>
                        {past ? "View recap" : "Flight details"}
                      </a>
                      {!past && (
                        <button
                          onClick={() => {
                            setForm({
                              origin: f.origin,
                              destination: f.destination,
                              departure: f.departure.slice(0, 16),
                              flightNumber: f.flightNumber,
                              scheduledArrival: f.arrivalScheduled
                                ? f.arrival
                                : undefined,
                            });
                            setEdit(f);
                          }}
                        >
                          Edit
                        </button>
                      )}
                      <button
                        disabled={busy}
                        aria-label={
                          "Remove " + f.origin + " to " + f.destination
                        }
                        onClick={() =>
                          action(async () => {
                            await privateApi(
                              endpoint + "/flights/" + f.slot,
                              "DELETE",
                              { revision: f.revision },
                            );
                            setEdit(undefined);
                            await refresh();
                          })
                        }
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </article>
                ))}
              </>
            )}
            {tab === "inbox" && (
              <>
                <button disabled={busy} onClick={() => action(refresh)}>
                  Refresh
                </button>
                <NoticeCentre
                  notices={data.inbox}
                  flights={data.flights}
                  busy={busy}
                  mark={(n) =>
                    void action(async () => {
                      await privateApi(
                        endpoint + "/notices/" + n.noticeId,
                        "PUT",
                        { read: !n.isRead },
                      );
                      await refresh();
                    })
                  }
                />
              </>
            )}
            {tab === "account" && (
              <>
                <TravelPreferences
                  prefs={data.preferences}
                  busy={busy}
                  onSave={(patch) =>
                    action(async () => {
                      await privateApi(endpoint + "/preferences", "PUT", {
                        channel: "passenger",
                        settings: patch,
                      });
                      await refresh();
                      setMessage("Preferences saved.");
                    })
                  }
                />
                <section className="pass-card">
                  <h2>Notifications</h2>
                  <p>Your route and departure time stay in SkyCalm.</p>
                  <div className="pass-row">
                    <span>Browser notifications</span>
                    <button disabled={busy} onClick={() => action(push)}>
                      {data.preferences.push ? "Disable push" : "Enable push"}
                    </button>
                  </div>
                  <div className="pass-row">
                    <span>Classroom email fallback</span>
                    <button
                      disabled={busy}
                      onClick={() =>
                        action(async () => {
                          await privateApi(endpoint + "/preferences", "PUT", {
                            channel: "email",
                            enabled: !data.preferences.email,
                          });
                          await refresh();
                        })
                      }
                    >
                      {data.preferences.email
                        ? "Disable email"
                        : "Enable email"}
                    </button>
                  </div>
                  <label className="pass-row notice-detail-choice">
                    <span>
                      Show turbulence levels in alerts
                      <small>
                        Email and browser notifications can then show the level
                        and how it may feel, even on a locked screen.
                      </small>
                    </span>
                    <input
                      type="checkbox"
                      checked={Boolean(data.preferences.explainAlerts)}
                      disabled={busy}
                      onChange={(e) => {
                        const enabled = e.target.checked;
                        action(async () => {
                          await privateApi(endpoint + "/preferences", "PUT", {
                            channel: "explainAlerts",
                            enabled,
                          });
                          await refresh();
                        });
                      }}
                    />
                  </label>
                </section>
                <section className="pass-card">
                  <h2>Account data</h2>
                  <p>Sign-in method · {signInMethod()}</p>
                  <p>
                    Your flights, forecast history and notifications are stored
                    in Stockholm. They disappear seven days after arrival. AWS
                    removes expired records in the following days. Your account
                    and delivery preferences stay until you delete them.
                  </p>
                  <div className="pass-actions">
                    <button disabled={busy} onClick={() => action(download)}>
                      <Download size={16} />
                      Export my data
                    </button>
                    <button onClick={() => setDeleting((v) => !v)}>
                      Delete account
                    </button>
                    <button onClick={() => setEndSessions(true)}>
                      Sign out all devices
                    </button>
                    <button onClick={() => signOut(settings.auth!)}>
                      Sign out
                    </button>
                  </div>
                  {endSessions && (
                    <div>
                      <p>End all your SkyCalm sessions, including this one?</p>
                      <button
                        disabled={busy}
                        onClick={() =>
                          action(async () => {
                            await privateApi(
                              endpoint + "/sign-out",
                              "POST",
                              {},
                            );
                            signOut(settings.auth!);
                          })
                        }
                      >
                        Confirm sign out everywhere
                      </button>
                      <button onClick={() => setEndSessions(false)}>
                        Keep sessions
                      </button>
                    </div>
                  )}
                  {deleting && (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        void action(async () => {
                          await privateApi(endpoint, "DELETE", { confirm });
                          signOut(settings.auth!);
                        });
                      }}
                    >
                      <label>
                        Type DELETE to permanently erase your saved flights,
                        inbox and login
                        <input
                          value={confirm}
                          onChange={(e) => setConfirm(e.target.value)}
                          autoComplete="off"
                        />
                      </label>
                      <button disabled={busy || confirm !== "DELETE"}>
                        Permanently delete
                      </button>
                    </form>
                  )}
                </section>
                {isAdmin() && <a href="/demo">Open demo controls</a>}
              </>
            )}
          </>
        ) : (
          <Skeleton label="Loading your flights…" />
        )}
      </div>
    </main>
  );
}

function Operator({
  path,
  flights,
  reload,
}: {
  path: string;
  flights: Flight[];
  reload: () => Promise<void>;
}) {
  const [run, setRun] = useState("gfs-20261124-12"),
    [slot, setSlot] = useState(1),
    [info, setInfo] = useState(""),
    [job, setJob] = useState(""),
    [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<{
    latestRun: string;
    model: string;
    manifestAvailable?: boolean;
    modelVersion?: number | null;
    observationsAsOf?: string | null;
    traffic: string;
    lastPush: number | null;
    queues: Record<string, number>;
  }>();
  useEffect(() => {
    if (path !== "/health") return;
    let alive = true;
    const update = () =>
      privateApi<NonNullable<typeof health>>("/api/admin/health")
        .then((h) => {
          if (alive) setHealth(h);
        })
        .catch((e) => {
          if (alive) setInfo(e.message);
        });
    void update();
    const t = setInterval(update, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [path]);
  useEffect(() => {
    if (!job) return;
    const until = Date.now() + 180000;
    const t = setInterval(() => {
      if (Date.now() > until) {
        clearInterval(t);
        setInfo("Replay is still processing. Check system health.");
        return;
      }
      privateApi<{ phase: string }>("/api/admin/jobs/" + job)
        .then((r) => {
          setInfo("Replay · " + r.phase);
          if (["ready", "failed"].includes(r.phase)) clearInterval(t);
        })
        .catch((e) => {
          setInfo(e.message);
          clearInterval(t);
        });
    }, 3500);
    return () => clearInterval(t);
  }, [job]);
  async function command(action: string) {
    setBusy(true);
    try {
      const r = await privateApi<{ jobId?: string }>(
        "/api/admin/actions",
        "POST",
        { requestId: crypto.randomUUID(), action, run, slot },
      );
      setInfo(
        action === "seed"
          ? "Three demo flights are ready."
          : "Request accepted.",
      );
      if (r.jobId) setJob(r.jobId);
      await reload();
    } catch (e) {
      setInfo(e instanceof Error ? e.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <nav className="pass-tabs">
        <a href="/flights">My flights</a>
        <a href={path === "/health" ? "/demo" : "/health"}>
          {path === "/health" ? "Demo controls" : "System health"}
        </a>
      </nav>
      <p role="status">{info}</p>
      {path === "/health" ? (
        health && (
          <section className="pass-card">
            <h2>Pipeline</h2>
            <PresenterAccessCheck />
            <p>Latest grid · {health.latestRun ?? "Unavailable"}</p>
            <p>
              Forecast method ·{" "}
              {health.modelVersion
                ? `LightGBM v${health.modelVersion} with physics fallback`
                : health.manifestAvailable
                  ? "Physics baseline"
                  : health.latestRun
                    ? "Grid details unavailable"
                    : "Awaiting first grid"}
            </p>
            <p>
              Weather observations ·{" "}
              {health.observationsAsOf
                ? time(health.observationsAsOf)
                : "No snapshot recorded"}
            </p>
            <p>Aircraft · {health.traffic}</p>
            <p>
              Last push accepted ·{" "}
              {health.lastPush
                ? time(new Date(health.lastPush * 1000).toISOString())
                : "No delivery recorded"}
            </p>
            {Object.entries(health.queues).map(([n, v]) => (
              <div key={n} className="pass-row">
                <span>{n}</span>
                <strong>{v}</strong>
              </div>
            ))}
          </section>
        )
      ) : (
        <>
          <section className="pass-card">
            <h2>Forecast replay</h2>
            <label>
              Archived run
              <select value={run} onChange={(e) => setRun(e.target.value)}>
                <option>gfs-20261124-12</option>
                <option>gfs-20261121-06</option>
              </select>
            </label>
            <button disabled={busy} onClick={() => command("publish")}>
              Publish replay
            </button>
          </section>
          <section className="pass-card">
            <h2>Classroom flights</h2>
            <label>
              Demo route
              <select
                value={slot}
                onChange={(e) => setSlot(Number(e.target.value))}
              >
                {flights
                  .filter((f) => f.watch === "demo")
                  .map((f) => (
                    <option key={f.slot} value={f.slot}>
                      {f.origin} → {f.destination}
                    </option>
                  ))}
              </select>
            </label>
            <div className="pass-actions">
              <button
                disabled={
                  busy ||
                  !flights.some((f) => f.watch === "demo" && f.slot === slot)
                }
                onClick={() => command("change")}
              >
                Inject test change
              </button>
              <button disabled={busy} onClick={() => command("push")}>
                Send test push
              </button>
              <button disabled={busy} onClick={() => command("seed")}>
                Reset demo flights
              </button>
            </div>
          </section>
        </>
      )}
    </>
  );
}
