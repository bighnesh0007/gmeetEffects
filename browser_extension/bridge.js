// Isolated-world relay between the page script (inject.js) and background.js.
(() => {
  let port = null;
  let wanted = false;

  function connect() {
    if (port || !wanted) return;
    port = chrome.runtime.connect({ name: "snapvanish" });
    port.onMessage.addListener((m) => window.postMessage({ __snapvanish_frame: true, ...m }, "*"));
    port.onDisconnect.addListener(() => {
      port = null;
      setTimeout(connect, 500); // service worker restarted; resume if still needed
    });
  }

  window.addEventListener("message", (e) => {
    if (e.source !== window || !e.data || !e.data.__snapvanish_ctl) return;
    if (e.data.__snapvanish_ctl === "start") {
      wanted = true;
      connect();
    } else if (e.data.__snapvanish_ctl === "stop") {
      wanted = false;
      if (port) {
        const p = port;
        port = null;
        p.disconnect();
      }
    }
  });
})();
