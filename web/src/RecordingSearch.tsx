import { useState } from "react";
import { ArrowLeft, Search } from "lucide-react";
import { RecordingResults } from "./RecordingResults";
import { searchRecordings } from "./recordings";

export default function RecordingSearch() {
  const params = new URLSearchParams(location.search);
  const [query, setQuery] = useState(() => params.get("q") ?? "");
  const [date, setDate] = useState(() => params.get("date") ?? "");
  const matches = searchRecordings(query, date);

  function filter(q: string, d: string) {
    setQuery(q);
    setDate(d);
    const next = new URLSearchParams();
    if (q) next.set("q", q);
    if (d) next.set("date", d);
    history.replaceState(
      null,
      "",
      next.size ? "/recordings?" + next : "/recordings",
    );
  }

  return (
    <>
      <header className="topbar">
        <div className="nav-inner">
          <a href="/" className="brand">
            <img src="/skycalm.svg" width="32" height="32" alt="" />
            SkyCalm
          </a>
          <a href="/" className="guide-button">
            <ArrowLeft size={16} /> Flight forecast
          </a>
        </div>
      </header>
      <main className="shell archive-search">
        <h1>Recorded flights</h1>
        <p>
          Find a flight by number, callsign or airport pair to replay its
          recorded path.
        </p>
        <form
          role="search"
          aria-label="Search recorded flights"
          onSubmit={(e) => e.preventDefault()}
        >
          <label>
            Flight or route
            <span className="archive-query">
              <Search size={17} aria-hidden="true" />
              <input
                type="search"
                value={query}
                maxLength={100}
                placeholder="Flight number, city or airport pair"
                onChange={(e) => filter(e.target.value, date)}
              />
            </span>
          </label>
          <label>
            Departure date (optional)
            <input
              type="date"
              value={date}
              onChange={(e) => filter(query, e.target.value)}
            />
          </label>
        </form>
        <p className="recording-count" role="status">
          {matches.length
            ? matches.length +
              (matches.length === 1 ? " recording" : " recordings")
            : "No recorded flights match these filters."}
        </p>
        {matches.length > 0 && <RecordingResults flights={matches} />}
        {(query || date) && (
          <button
            type="button"
            className="guide-button"
            onClick={() => filter("", "")}
          >
            Clear filters
          </button>
        )}
      </main>
    </>
  );
}
