import { useState } from "react";
import AirportField from "./AirportField";
import { guide, knownLevel, LevelButton } from "./CabinGuide";
import { clocks, flightHref, noticeNames } from "./journey";
import type { Flight, Notice, Preferences } from "./journey";
import type { Airport } from "./types";

export function airportLabel(code: string): Airport | null {
  return code
    ? { code, city: code, name: code, country: "", lat: 0, lon: 0 }
    : null;
}
export function TravelPreferences({
  prefs,
  onSave,
  busy,
}: {
  prefs: Preferences;
  onSave: (patch: Partial<Preferences>) => Promise<void>;
  busy: boolean;
}) {
  const local = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const [value, set] = useState<Preferences>({ ...prefs }),
    [quiet, setQuiet] = useState(Boolean(prefs.quietHours));
  const [hours, setHours] = useState(
    prefs.quietHours ?? { start: "22:00", end: "07:00", zone: local },
  );
  const [home, setHome] = useState(airportLabel(prefs.homeAirport ?? ""));
  const zones = Array.from(
    new Set([local, "UTC", hours.zone, ...Intl.supportedValuesOf("timeZone")]),
  ).sort();
  return (
    <form
      className="pass-card travel-prefs"
      onSubmit={(e) => {
        e.preventDefault();
        void onSave({
          timeDisplay: value.timeDisplay ?? "local",
          altitudeUnit: value.altitudeUnit ?? "ft",
          sensitivity: value.sensitivity ?? "all",
          nervousFlyer: !!value.nervousFlyer,
          homeAirport: home?.code ?? "",
          quietHours: quiet ? hours : null,
        });
      }}
    >
      <h2>Travel preferences</h2>
      <div className="settings-grid">
        <label>
          Alert sensitivity
          <select
            value={value.sensitivity ?? "all"}
            onChange={(e) =>
              set({
                ...value,
                sensitivity: e.target.value as Preferences["sensitivity"],
              })
            }
          >
            <option value="all">All forecast changes</option>
            <option value="moderate">Moderate or worse</option>
          </select>
        </label>
        <label>
          Clock preference
          <select
            value={value.timeDisplay ?? "local"}
            onChange={(e) =>
              set({
                ...value,
                timeDisplay: e.target.value as Preferences["timeDisplay"],
              })
            }
          >
            <option value="local">Airport local time first</option>
            <option value="utc">UTC first</option>
          </select>
        </label>
        <label>
          Altitude units
          <select
            value={value.altitudeUnit ?? "ft"}
            onChange={(e) =>
              set({
                ...value,
                altitudeUnit: e.target.value as Preferences["altitudeUnit"],
              })
            }
          >
            <option value="ft">Feet</option>
            <option value="m">Metres</option>
          </select>
        </label>
        <div>
          <AirportField
            label="Home airport"
            selected={home}
            onChange={setHome}
          />
          {home && (
            <button type="button" onClick={() => setHome(null)}>
              Clear home airport
            </button>
          )}
        </div>
      </div>
      <label className="inline-check">
        <input
          type="checkbox"
          checked={!!value.nervousFlyer}
          onChange={(e) => set({ ...value, nervousFlyer: e.target.checked })}
        />
        Show extra cabin guidance
      </label>
      <label className="inline-check">
        <input
          type="checkbox"
          checked={quiet}
          onChange={(e) => setQuiet(e.target.checked)}
        />
        Quiet hours for email and browser alerts
      </label>
      {quiet && (
        <>
          <div className="settings-grid">
            <label>
              Quiet from
              <input
                type="time"
                required
                value={hours.start}
                onChange={(e) => setHours({ ...hours, start: e.target.value })}
              />
            </label>
            <label>
              Quiet until
              <input
                type="time"
                required
                value={hours.end}
                onChange={(e) => setHours({ ...hours, end: e.target.value })}
              />
            </label>
            <label>
              Quiet-hours time zone
              <select
                value={hours.zone}
                onChange={(e) => setHours({ ...hours, zone: e.target.value })}
              >
                {zones.map((z) => (
                  <option key={z}>{z}</option>
                ))}
              </select>
            </label>
          </div>
          <p>Updates during these hours stay in your notification centre.</p>
        </>
      )}
      <button className="pass-primary" disabled={busy}>
        Save preferences
      </button>
    </form>
  );
}
export function SetupChecklist({
  hasFlight,
  notifications,
  add,
  account,
}: {
  hasFlight: boolean;
  notifications: boolean;
  add: () => void;
  account: () => void;
}) {
  const [help, setHelp] = useState(false),
    [hidden, setHidden] = useState(() => {
      try {
        return localStorage.getItem("skycalm-setup-dismissed") === "1";
      } catch {
        return false;
      }
    });
  const installed =
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone;
  if (hidden || (hasFlight && notifications && installed)) return null;
  const ua = navigator.userAgent;
  const steps = /iPhone|iPad/.test(ua)
    ? "In Safari, open Share, choose Add to Home Screen and confirm."
    : /Android/.test(ua)
      ? "In Chrome, open the menu and choose Install app or Add to home screen."
      : /Safari/.test(ua) && !/Chrome|Chromium|Edg/.test(ua)
        ? "In Safari, choose File → Add to Dock."
        : "Open your browser menu and choose Install SkyCalm, or use the install icon in the address bar.";
  return (
    <details className="pass-card setup-checklist">
      <summary>
        Getting started ·{" "}
        {[hasFlight, notifications, installed].filter(Boolean).length}/3
        complete
      </summary>
      <ol>
        <li>
          {hasFlight ? (
            "Flight saved"
          ) : (
            <button onClick={add}>Save your first flight</button>
          )}
        </li>
        <li>
          {notifications ? (
            "Notifications enabled"
          ) : (
            <button onClick={account}>Set up notifications</button>
          )}
        </li>
        <li>
          {installed ? (
            "App installed"
          ) : (
            <button onClick={() => setHelp(!help)}>Install SkyCalm</button>
          )}
          {help && <p>{steps}</p>}
        </li>
      </ol>
      <button
        onClick={() => {
          setHidden(true);
          try {
            localStorage.setItem("skycalm-setup-dismissed", "1");
          } catch {
            /* Private mode. */
          }
        }}
      >
        Hide setup
      </button>
    </details>
  );
}
export function NoticeCentre({
  notices,
  flights,
  mark,
  busy,
}: {
  notices: Notice[];
  flights: Flight[];
  mark: (notice: Notice) => void;
  busy: boolean;
}) {
  const [unread, setUnread] = useState(false);
  const groups = new Map<string, Notice[]>();
  for (const n of notices.filter((n) => !unread || !n.isRead)) {
    const group = n.flightId ?? n.flightRevision ?? "account";
    groups.set(group, [...(groups.get(group) ?? []), n]);
  }
  return (
    <section className="pass-card">
      <h2>Notification centre</h2>
      <label className="inline-check">
        <input
          type="checkbox"
          checked={unread}
          onChange={(e) => setUnread(e.target.checked)}
        />
        Unread only
      </label>
      {!groups.size && (
        <p>
          {unread
            ? "You’re all caught up."
            : "Flight reminders and forecast changes will appear here."}
        </p>
      )}
      {[...groups.entries()].map(([id, items]) => {
        const f = flights.find((f) => f.id === id),
          name = f
            ? f.origin + " → " + f.destination
            : (items[0].routeLabel ??
              (id === "account" ? "Account updates" : "Previous flight"));
        return (
          <section className="notice-group" key={id}>
            <h3>{f ? <a href={flightHref(id)}>{name}</a> : name}</h3>
            {items.map((n) => (
              <article className="pass-notice" key={n.noticeId}>
                <div>
                  <strong>{noticeNames[n.kind] ?? "Flight update"}</strong>{" "}
                  {!n.isRead && <small>Unread</small>}
                  {n.peak && knownLevel(n.peak) && (
                    <p>
                      <LevelButton level={n.peak} marker /> ·{" "}
                      {guide.levels[n.peak].summary}
                    </p>
                  )}
                  <p>
                    {new Date(n.created * 1000).toLocaleString("en-GB", {
                      timeZone: "UTC",
                      day: "numeric",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}{" "}
                    UTC ·{" "}
                    {n.delivery === "push"
                      ? "Sent to browser"
                      : n.delivery === "email"
                        ? "Sent by email"
                        : "In-app"}
                  </p>
                  {n.sentBody && (
                    <details>
                      <summary>Delivered message</summary>
                      <p className="delivered-copy">{n.sentBody}</p>
                    </details>
                  )}
                  <button disabled={busy} onClick={() => mark(n)}>
                    {n.isRead ? "Mark unread" : "Mark read"}
                  </button>
                </div>
              </article>
            ))}
          </section>
        );
      })}
    </section>
  );
}
export function PastCard({ f, prefs }: { f: Flight; prefs: Preferences }) {
  return (
    <small>
      {f.expiresAt
        ? "Recap available until " +
          clocks(
            new Date(f.expiresAt * 1000).toISOString(),
            f.destination,
            prefs.timeDisplay,
          )
        : "Recap available for seven days after arrival."}
    </small>
  );
}
