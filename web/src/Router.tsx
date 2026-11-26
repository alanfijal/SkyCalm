import { lazy, Suspense, useEffect, useState } from "react";
import { config, finishSignIn } from "./passengerAuth";
const App = lazy(() => import("./App"));
const Passengers = lazy(() => import("./Passengers"));
const RouteHistory = lazy(() => import("./RouteHistory"));
const RecordedFlight = lazy(() => import("./RecordedFlight"));
const pages = ["/", "/flights", "/demo", "/health", "/history", "/replay"];
export default function Router() {
  const [path, setPath] = useState(location.pathname),
    [error, setError] = useState("");
  useEffect(() => {
    const update = () => setPath(location.pathname);
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
        to.search ||
        to.hash
      )
        return;
      e.preventDefault();
      history.pushState(null, "", to.pathname);
      setPath(to.pathname);
      window.scrollTo(0, 0);
    };
    const inbox = (e: MessageEvent) => {
      if (e.data?.type === "open-inbox") {
        history.pushState(null, "", "/flights?view=inbox");
        setPath("/flights");
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
        setPath(location.pathname);
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
  if (path === "/replay")
    return (
      <Suspense fallback={<main>Loading the recorded flight…</main>}>
        <RecordedFlight />
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
        key={path + version + error}
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
