import { createRoot } from "react-dom/client";
import "@fontsource-variable/dm-sans/wght.css";
import "./styles.css";
import Router from "./Router";
import { CabinGuideProvider } from "./CabinGuide";
createRoot(document.getElementById("root")!).render(
  <CabinGuideProvider>
    <Router />
  </CabinGuideProvider>,
);
if ("serviceWorker" in navigator)
  navigator.serviceWorker.register("/service-worker.js").catch(() => {});
