// Pulls processed frames from the local Snap Vanish app and pushes them to the
// Meet tab over a port. The fetch runs here (not in the page) because the
// extension has host permission for 127.0.0.1, so Chrome's local-network
// restrictions on web pages do not apply.
const APP = "http://127.0.0.1:8765";

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "snapvanish") return;
  let open = true;
  port.onDisconnect.addListener(() => (open = false));

  (async () => {
    let since = "";
    while (open) {
      try {
        // Long-poll: the app answers as soon as a newer frame exists.
        const r = await fetch(`${APP}/frame.jpg?since=${since}`, { cache: "no-store" });
        if (r.status === 200) {
          since = r.headers.get("X-Frame-Id") || "";
          const jpeg = toBase64(await r.arrayBuffer());
          if (open) port.postMessage({ ok: true, jpeg });
        }
      } catch (e) {
        if (open) port.postMessage({ ok: false });
        await sleep(1000);
      }
    }
  })();
});
