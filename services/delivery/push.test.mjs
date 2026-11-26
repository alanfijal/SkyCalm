import assert from "node:assert/strict";
import test from "node:test";
import { send } from "./index.mjs";
import guide from "./turbulence.json" with { type: "json" };
const packet = {
  subscription: { endpoint: "https://fcm.googleapis.com/fcm/send/example" },
  test: true,
  tag: "inbox-item",
};
test("sends only generic information and bounds lifetime", async () => {
  const result = await send(
    packet,
    async () => ({}),
    async (_sub, data, opts) => {
      assert.deepEqual(Object.keys(JSON.parse(data)).sort(), [
        "body",
        "tag",
        "title",
      ]);
      assert.equal(opts.TTL, 300);
    },
  );
  assert.equal(result.result, "push");
  assert.equal(result.body, "A test update is waiting in your inbox. " + guide.seatbelt);
});
test("expired subscriptions and recoverable failures are distinguished", async () => {
  for (const [status, expected] of [
    [410, "gone"],
    [429, "retry"],
    [500, "retry"],
  ]) {
    const out = await send(
      packet,
      async () => ({}),
      async () => {
        throw Object.assign(new Error(), { statusCode: status });
      },
    );
    assert.equal(out.result, expected);
  }
});
test("lock-screen copy uses only the approved level and keeps the trip private", async () => {
  for (const level of [
    "smooth",
    "light",
    "moderate",
    "severe",
    "unavailable",
    "__proto__",
    undefined,
  ]) {
    await send(
      { ...packet, level, origin: "EDI", flightNumber: "SK1234" },
      async () => ({}),
      async (_sub, data) => {
        const { body } = JSON.parse(data);
        assert.ok(body.includes(guide.seatbelt));
        assert.ok(body.length < 175);
        assert.doesNotMatch(body, /EDI|SK1234/);
        if (["smooth", "light", "moderate", "severe"].includes(level)) {
          assert.ok(body.includes(guide.levels[level].summary));
        } else {
          assert.equal(
            body,
            "A test update is waiting in your inbox. " + guide.seatbelt,
          );
        }
      },
    );
  }
});
test("only supported push services receive a request", async () => {
  await assert.rejects(
    send(
      { ...packet, subscription: { endpoint: "https://example.org/path" } },
      () => assert.fail(),
      () => assert.fail(),
    ),
  );
});
