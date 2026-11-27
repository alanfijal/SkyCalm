self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  // Existing installations may still have a subscription from the browser-alert release.
  event.waitUntil(
    (async () => {
      try {
        const subscription =
          await self.registration.pushManager?.getSubscription();
        if (subscription) await subscription.unsubscribe();
      } catch {
        // Some browsers disable subscription access after the user revokes permission.
      }
    })(),
  );
});
