import { runInNewContext } from "node:vm";
import { expect, test, vi } from "vitest";
import worker from "../public/service-worker.js?raw";

type LifecycleEvent = { waitUntil: (work: Promise<unknown>) => void };

async function activate(getSubscription?: () => Promise<unknown>) {
  const listeners = new Map<string, (event: LifecycleEvent) => void>();
  runInNewContext(worker, {
    self: {
      registration: { pushManager: getSubscription && { getSubscription } },
      addEventListener: (
        name: string,
        handle: (event: LifecycleEvent) => void,
      ) => listeners.set(name, handle),
    },
  });
  const work: Promise<unknown>[] = [];
  listeners.get("activate")!({ waitUntil: (pending) => work.push(pending) });
  await Promise.all(work);
  return listeners;
}

test("updating an older installation unsubscribes its browser endpoint", async () => {
  const unsubscribe = vi.fn().mockResolvedValue(true);
  const listeners = await activate(async () => ({ unsubscribe }));
  expect(unsubscribe).toHaveBeenCalledOnce();
  expect(listeners.has("push")).toBe(false);
});

test("activation works with revoked permission or without push support", async () => {
  await activate(async () => {
    throw new Error("Permission revoked");
  });
  await activate();
});
