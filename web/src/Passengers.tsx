import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  Bell,
  CalendarClock,
  ChevronRight,
  Download,
  Plane,
  Plus,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import {
  canOperate,
  config,
  isAdmin,
  privateApi,
  signedIn,
  signIn,
  signOut,
  type Settings,
} from "./passengerAuth";
import { dateLabel, clock } from "./types";
import "./passengers.css";
import { clearDraft, draft } from "./flightDraft";

interface Flight {
  slot: number;
  id: string;
  revision: string;
  origin: string;
  destination: string;
  departure: string;
  arrival: string;
  watch: string;
  assessment?: { peak: string };
}
interface Notice {
  noticeId: string;
  kind: string;
  created: number;
  delivery: string;
  slot?: number;
}
interface Overview {
  closing?: boolean;
  flights: Flight[];
  inbox: Notice[];
  preferences: { email: boolean; push: boolean };
}
const names: Record<string, string> = {
  "forecast-change": "Forecast changed",
  "reminder-24h": "24 hours until departure",
  "reminder-3h": "3 hours until departure",
  "test-change": "Demo forecast changed",
  "test-push": "Test notification",
};
const time = (d: string) => dateLabel(d) + " · " + clock(d) + " UTC";
const endpoint = "/api/me";
const freshForm = () => ({
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
  async function save() {
    const slot =
      edit?.slot ??
      Array.from({ length: 8 }, (_, i) => i + 1).find(
        (s) => !data?.flights.some((f) => f.slot === s),
      );
    if (!slot) throw Error("You can save eight flights.");
    await privateApi(endpoint + "/flights/" + slot, "PUT", {
      ...form,
      departure: new Date(form.departure + "Z").toISOString(),
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
        <a href="/">
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
          <p>Loading…</p>
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
                      ? "Inbox"
                      : "Account"}
                  {t === "inbox" && data.inbox.length > 0
                    ? " (" + data.inbox.length + ")"
                    : ""}
                </button>
              ))}
            </nav>
            {tab === "flights" && (
              <>
                <div className="pass-row">
                  <h2>Upcoming routes</h2>
                  {edit === undefined && (
                    <button
                      className="pass-primary"
                      disabled={data.flights.length >= 8}
                      onClick={() => {
                        setForm(freshForm());
                        setEdit(null);
                      }}
                    >
                      <Plus size={16} /> Add flight
                    </button>
                  )}
                </div>
                {edit !== undefined && (
                  <form
                    className="pass-card pass-form"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void action(save);
                    }}
                  >
                    <h3>{edit ? "Edit flight" : "Add a flight"}</h3>
                    <div className="pass-fields">
                      {(["origin", "destination"] as const).map((k, i) => (
                        <label key={k}>
                          {i ? "To" : "From"}
                          <input
                            aria-label={
                              i
                                ? "Arrival airport code"
                                : "Departure airport code"
                            }
                            placeholder={i ? "OPO" : "EDI"}
                            minLength={3}
                            maxLength={3}
                            pattern="[A-Za-z]{3}"
                            required
                            value={form[k]}
                            onChange={(e) =>
                              setForm({
                                ...form,
                                [k]: e.target.value.toUpperCase(),
                              })
                            }
                          />
                        </label>
                      ))}
                      <label>
                        Departure · UTC
                        <input
                          type="datetime-local"
                          required
                          value={form.departure}
                          onChange={(e) =>
                            setForm({ ...form, departure: e.target.value })
                          }
                        />
                      </label>
                    </div>
                    <div className="pass-actions">
                      <button disabled={busy} className="pass-primary">
                        Save flight
                      </button>
                      <button type="button" onClick={() => setEdit(undefined)}>
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
                {!data.flights.length && edit === undefined && (
                  <section className="pass-card">
                    <Plane />
                    <h3>No saved flights yet</h3>
                    <p>
                      Add the airports and departure time for your next trip.
                    </p>
                  </section>
                )}
                {data.flights.map((f) => (
                  <article className="pass-card pass-route" key={f.id}>
                    <div>
                      <h3>
                        {f.origin} <ChevronRight size={16} /> {f.destination}
                      </h3>
                      <p>
                        <CalendarClock size={15} /> {time(f.departure)}
                      </p>
                      {f.assessment && (
                        <small>
                          {f.watch === "demo" ? "Demo · " : ""}
                          {f.assessment.peak} conditions
                        </small>
                      )}
                    </div>
                    <div className="pass-actions">
                      <button
                        disabled={busy}
                        onClick={() => {
                          setForm({
                            origin: f.origin,
                            destination: f.destination,
                            departure: f.departure.slice(0, 16),
                          });
                          setEdit(f);
                        }}
                      >
                        Edit
                      </button>
                      <button
                        aria-label={
                          "Remove " + f.origin + " to " + f.destination
                        }
                        disabled={busy}
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
              <section className="pass-card">
                <div className="pass-row">
                  <h2>Flight updates</h2>
                  <button disabled={busy} onClick={() => action(refresh)}>
                    Refresh
                  </button>
                </div>
                {data.inbox.length ? (
                  data.inbox.map((n) => (
                    <article className="pass-notice" key={n.noticeId}>
                      <Bell size={17} />
                      <div>
                        <strong>{names[n.kind] ?? "Flight update"}</strong>
                        <p>
                          {time(new Date(n.created * 1000).toISOString())} ·{" "}
                          {n.delivery === "push"
                            ? "Sent to browser"
                            : n.delivery === "email"
                              ? "Sent by email"
                              : "In-app"}
                        </p>
                      </div>
                    </article>
                  ))
                ) : (
                  <p>Your reminders and forecast changes will appear here.</p>
                )}
              </section>
            )}
            {tab === "account" && (
              <>
                <section className="pass-card">
                  <h2>Notifications</h2>
                  <p>
                    Alerts say that an update is waiting. Your route and
                    departure time stay in SkyCalm.
                  </p>
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
                </section>
                <section className="pass-card">
                  <h2>Account data</h2>
                  <p>
                    Flight records expire seven days after estimated arrival.
                  </p>
                  <div className="pass-actions">
                    <button disabled={busy} onClick={() => action(download)}>
                      <Download size={16} />
                      Export my data
                    </button>
                    <button onClick={() => setDeleting((v) => !v)}>
                      Delete account
                    </button>
                    <button onClick={() => signOut(settings.auth!)}>
                      Sign out
                    </button>
                  </div>
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
          <p>Loading your flights…</p>
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
            <p>Latest grid · {health.latestRun ?? "Unavailable"}</p>
            <p>
              Forecast method ·{" "}
              {health.modelVersion
                ? `LightGBM v${health.modelVersion} with physics fallback`
                : health.latestRun
                  ? "Physics baseline"
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
