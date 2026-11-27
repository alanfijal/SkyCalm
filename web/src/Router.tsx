import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { PageSkeleton } from "./PageSkeleton";
const Landing = lazy(() => import("./Landing"));
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
  "/forecast",
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
  const previous = useRef(page);
  useEffect(() => {
    if (previous.current === page) return;
    previous.current = page;
    const focusHeading = () => {
      const title = document.querySelector<HTMLElement>("main h1");
      if (!title || !title.getClientRects().length || title.closest("[hidden]"))
        return false;
      title.tabIndex = -1;
      title.focus({ preventScroll: true });
      return true;
    };
    if (focusHeading()) return;
    const observer = new MutationObserver(() => {
      if (focusHeading()) observer.disconnect();
    });
    observer.observe(document.getElementById("root")!, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["style", "hidden"],
    });
    return () => observer.disconnect();
  }, [page]);
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
    window.addEventListener("popstate", update);
    document.addEventListener("click", anchor);
    const url = new URL(location.href);
    if (url.searchParams.has("code") || url.searchParams.has("error")) {
      history.replaceState(null, "", "/flights");
      setPath("/flights");
      (async () => {
        const { config, finishSignIn } = await import("./passengerAuth");
        const c = await config();
        if (!c.auth) throw Error("Sign-in is unavailable.");
        const p = await finishSignIn(c.auth, url);
        history.replaceState(null, "", p);
        setPath(currentPage());
        setVersion((n) => n + 1);
      })().catch((e) => setError(e.message));
    }
    return () => {
      window.removeEventListener("popstate", update);
      document.removeEventListener("click", anchor);
    };
  }, []);
  const [version, setVersion] = useState(0);
  if (path === "/")
    return (
      <Suspense fallback={<PageSkeleton label="Opening SkyCalm" />}>
        <Landing />
      </Suspense>
    );
  if (path === "/shared")
    return (
      <Suspense fallback={<PageSkeleton label="Opening forecast…" />}>
        <SharedFlight />
      </Suspense>
    );
  if (path === "/recordings")
    return (
      <Suspense fallback={<PageSkeleton label="Loading recorded flights…" />}>
        <RecordingSearch key={page} />
      </Suspense>
    );
  if (path === "/replay")
    return (
      <Suspense
        fallback={<PageSkeleton label="Loading the recorded flight…" />}
      >
        <RecordedFlight
          key={page}
          id={new URLSearchParams(query).get("flight")}
        />
      </Suspense>
    );
  if (path === "/history")
    return (
      <Suspense fallback={<PageSkeleton label="Loading route history…" />}>
        <RouteHistory />
      </Suspense>
    );
  return pages.slice(2).includes(path) ? (
    <Suspense fallback={<PageSkeleton label="Loading…" />}>
      <Passengers
        key={page + version + error}
        path={path}
        initialError={error}
      />
    </Suspense>
  ) : (
    <Suspense fallback={<PageSkeleton label="Loading forecast…" />}>
      <App />
    </Suspense>
  );
}
