import { createRoot } from "react-dom/client";
import "@fontsource-variable/dm-sans";
import "./styles.css";
import Router from "./Router";
createRoot(document.getElementById("root")!).render(<Router />);
if ("serviceWorker" in navigator)
  navigator.serviceWorker.register("/service-worker.js").catch(() => {});
