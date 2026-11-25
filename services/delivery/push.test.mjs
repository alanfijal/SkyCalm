import assert from "node:assert/strict";
import test from "node:test";
import { send } from "./index.mjs";
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
test("only supported push services receive a request", async () => {
  await assert.rejects(
    send(
      { ...packet, subscription: { endpoint: "https://example.org/path" } },
      () => assert.fail(),
      () => assert.fail(),
    ),
  );
});
