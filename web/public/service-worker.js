self.addEventListener("push", (event) => {
  let update = {};
  try {
    update = event.data?.json() || {};
  } catch {
    /* use the generic message */
  }
  event.waitUntil(
    self.registration.showNotification("SkyCalm", {
      body: update.body || "A flight update is waiting in your inbox.",
      icon: "/icon-192.png",
      tag: update.tag,
      data: { path: "/flights?view=inbox" },
    }),
  );
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    (async () => {
      const url = new URL("/flights?view=inbox", self.location.origin).href;
      const windows = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      const open = windows.find(
        (w) => new URL(w.url).origin === self.location.origin,
      );
      if (open) {
        await open.focus();
        open.postMessage({ type: "open-inbox" });
      } else await self.clients.openWindow(url);
    })(),
  );
});
