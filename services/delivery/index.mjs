import { sendNotification } from "web-push";
import { GetSecretValueCommand, SecretsManagerClient } from "@aws-sdk/client-secrets-manager";

const client = new SecretsManagerClient({ maxAttempts: 2 });
let cached;
async function signingKey() {
  if (!cached || cached.until < Date.now()) {
    const { SecretString } = await client.send(new GetSecretValueCommand({ SecretId: process.env.VAPID_SECRET }));
    const { publicKey, privateKey } = JSON.parse(SecretString);
    cached = { until: Date.now() + 300000, value: { subject: process.env.VAPID_SUBJECT, publicKey, privateKey } };
  }
  return cached.value;
}

export async function send({ subscription, test, tag }, getKey, transmit) {
  const target = new URL(subscription.endpoint);
  const provider = target.hostname === "fcm.googleapis.com" ||
    [".push.services.mozilla.com", ".push.apple.com", ".notify.windows.com"].some(s => target.hostname.endsWith(s));
  if (target.protocol !== "https:" || !provider || target.username || target.password || target.port || target.hash) {
    throw new Error("Unsupported push endpoint");
  }
  const vapidDetails = await getKey();
  const payload = JSON.stringify({ title: "SkyCalm", body: test ? "A test update is waiting in your inbox." : "A flight update is waiting in your inbox.", tag });
  try {
    await transmit(subscription, payload, { vapidDetails, TTL: 300, timeout: 5000, urgency: "normal" });
    return { result: "push" };
  } catch (error) {
    if ([404, 410].includes(error.statusCode)) return { result: "gone" };
    if (error.statusCode === 400) return { result: "gone" };
    return { result: "retry" };
  }
}

export const handler = (event) => send(event, signingKey, sendNotification);
