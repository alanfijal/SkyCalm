// Messaging crawlers get the preview. Only the recipient's browser holds the full grant.
if (/^#[a-f0-9]{32}\.[a-f0-9]{64}$/.test(location.hash)) {
  const target = new URL("/shared", document.currentScript.src);
  target.hash = location.hash;
  location.replace(target.href);
}
