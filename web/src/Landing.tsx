import { useState } from "react";
import { ArrowRight, Globe2, Moon, Play, Sun } from "lucide-react";
import { RoutePrint, exampleTrack } from "./RoutePrint";
import { startLookup } from "./lookupDraft";
import { localDate } from "./flightSchedule";
import { applyTheme } from "./theme";
import "./landing.css";

export default function Landing() {
  const [light, setLight] = useState(
    document.documentElement.dataset.theme === "light",
  );
  const [error, setError] = useState("");
  return (
    <div className="welcome">
      <a className="skip-link" href="#flight-search">
        Skip to flight search
      </a>
      <header className="topbar">
        <nav className="welcome-nav" aria-label="Main navigation">
          <a className="brand" href="/">
            <img src="/skycalm.svg" alt="" width="34" height="34" />
            SkyCalm
          </a>
          <div>
            <a href="/recordings">Recorded flights</a>
            <a href="/flights">My flights</a>
            <button
              className="theme-toggle"
              aria-label={
                light ? "Switch to dark theme" : "Switch to light theme"
              }
              onClick={() => {
                applyTheme(light ? "dark" : "light");
                setLight(!light);
              }}
            >
              {light ? <Moon size={18} /> : <Sun size={18} />}
            </button>
          </div>
        </nav>
      </header>
      <main className="welcome-main">
        <section className="welcome-entry" aria-labelledby="welcome-title">
          <h1 id="welcome-title">
            See how your
            <br />
            flight may feel<span>.</span>
          </h1>
          <p>
            Explore the turbulence forecast along your flight across Europe.
          </p>
          <form
            id="flight-search"
            tabIndex={-1}
            aria-label="Flight number search"
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              try {
                startLookup(
                  String(f.get("number")).trim().toUpperCase(),
                  String(f.get("date")),
                );
                history.pushState(null, "", "/forecast");
                window.dispatchEvent(new PopStateEvent("popstate"));
                window.scrollTo(0, 0);
              } catch {
                setError(
                  "Open the airport forecast to search without browser storage.",
                );
              }
            }}
          >
            <label>
              Flight number
              <input
                required
                name="number"
                maxLength={12}
                pattern="[A-Za-z0-9 ]{2,12}"
                autoComplete="off"
                autoCapitalize="characters"
                placeholder="e.g. KL1521"
              />
            </label>
            <label>
              Departure date
              <input
                required
                name="date"
                type="date"
                defaultValue={localDate()}
              />
            </label>
            <button className="submit" type="submit">
              Find my flight <ArrowRight size={18} />
            </button>
          </form>
          {error && <p role="alert">{error}</p>}
          <a className="airport-entry" href="/forecast">
            <Globe2 size={17} /> Search by airports <ArrowRight size={15} />
          </a>
        </section>
        <section className="welcome-replay" aria-labelledby="replay-heading">
          <div className="welcome-map">
            <RoutePrint
              samples={exampleTrack}
              from="CTA"
              to="LIN"
              label="Recorded flight AZ1704 from Catania to Milan, coloured by its archived turbulence forecast."
            />
          </div>
          <div className="welcome-route">
            <div>
              <p>Recorded flight · AZ1704</p>
              <h2 id="replay-heading">Catania to Milan</h2>
              <span>21 Nov 2026 · 1 h 49 min</span>
            </div>
            <a href="/replay" className="example-play">
              <Play size={18} fill="currentColor" /> Open replay
            </a>
          </div>
        </section>
      </main>
      <footer className="welcome-foot">
        <span>Weather from NOAA GFS</span>
        <span>
          For passenger education only. Do not use for navigation, flight
          planning or safety decisions.
        </span>
      </footer>
    </div>
  );
}
