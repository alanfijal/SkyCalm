import { lazy, Suspense, useEffect, useState } from "react";
import { config, finishSignIn } from "./passengerAuth";
const App = lazy(() => import("./App"));
const Passengers = lazy(() => import("./Passengers"));
const SharedFlight = lazy(() =>
  import("./FlightJourney").then((m) => ({ default: m.SharedFlight })),
);
const RouteHistory = lazy(() => import("./RouteHistory"));
const RecordedFlight = lazy(() => import("./RecordedFlight"));
const RecordingSearch = lazy(() => import("./RecordingSearch"));
const pages = [
  "/",
  "/flights",
  "/shared",
  "/demo",
  "/health",
  "/history",
  "/replay",
  "/recordings",
];
const currentPage = () => location.pathname + location.search;
export default function Router() {
  const [page, setPath] = useState(currentPage),
    [error, setError] = useState("");
  const [path, query = ""] = page.split("?");
  useEffect(() => {
    const update = () => setPath(currentPage());
    const anchor = (e: MouseEvent) => {
      const a = e.target instanceof Element ? e.target.closest("a") : null;
      if (
        !a ||
        !a.href ||
        e.defaultPrevented ||
        e.button !== 0 ||
        e.metaKey ||
        e.ctrlKey ||
        e.shiftKey ||
        e.altKey ||
        a.target ||
        a.download
      )
        return;
      const to = new URL(a.href);
      if (
        to.origin !== location.origin ||
        !pages.includes(to.pathname) ||
        (to.search &&
          !["/replay", "/recordings", "/flights"].includes(to.pathname)) ||
        to.hash
      )
        return;
      e.preventDefault();
      history.pushState(null, "", to.pathname + to.search);
      setPath(currentPage());
      window.scrollTo(0, 0);
    };
    const inbox = (e: MessageEvent) => {
      if (e.data?.type === "open-inbox") {
        history.pushState(null, "", "/flights?view=inbox");
        setPath(currentPage());
        setVersion((n) => n + 1);
      }
    };
    navigator.serviceWorker?.addEventListener("message", inbox);
    window.addEventListener("popstate", update);
    document.addEventListener("click", anchor);
    const url = new URL(location.href);
    if (url.searchParams.has("code") || url.searchParams.has("error")) {
      history.replaceState(null, "", "/flights");
      setPath("/flights");
      (async () => {
        const c = await config();
        if (!c.auth) throw Error("Sign-in is unavailable.");
        const p = await finishSignIn(c.auth, url);
        history.replaceState(null, "", p);
        setPath(currentPage());
        setVersion((n) => n + 1);
      })().catch((e) => setError(e.message));
    }
    return () => {
      navigator.serviceWorker?.removeEventListener("message", inbox);
      window.removeEventListener("popstate", update);
      document.removeEventListener("click", anchor);
    };
  }, []);
  const [version, setVersion] = useState(0);
  if (path === "/shared")
    return (
      <Suspense fallback={<main>Opening forecast…</main>}>
        <SharedFlight />
      </Suspense>
    );
  if (path === "/recordings")
    return (
      <Suspense fallback={<main>Loading recorded flights…</main>}>
        <RecordingSearch key={page} />
      </Suspense>
    );
  if (path === "/replay")
    return (
      <Suspense fallback={<main>Loading the recorded flight…</main>}>
        <RecordedFlight
          key={page}
          id={new URLSearchParams(query).get("flight")}
        />
      </Suspense>
    );
  if (path === "/history")
    return (
      <Suspense fallback={<main>Loading route history…</main>}>
        <RouteHistory />
      </Suspense>
    );
  return pages.slice(1).includes(path) ? (
    <Suspense fallback={<main>Loading…</main>}>
      <Passengers
        key={page + version + error}
        path={path}
        initialError={error}
      />
    </Suspense>
  ) : (
    <Suspense fallback={<main>Loading forecast…</main>}>
      <App />
    </Suspense>
  );
}
