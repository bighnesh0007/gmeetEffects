// Runs in Google Meet's own page context. Adds a "Snap Vanish Camera" device and
// answers camera requests for it with a canvas stream fed by the local app.
(() => {
  const DEVICE_ID = "snap-vanish-camera";
  const LABEL = "Snap Vanish Camera";
  const md = navigator.mediaDevices;
  if (!md || md.__snapVanish) return;
  md.__snapVanish = true;

  const origGetUserMedia = md.getUserMedia.bind(md);
  const origEnumerate = md.enumerateDevices.bind(md);

  let canvas = null;
  let ctx = null;
  let users = 0;
  let lastFrame = 0;
  let live = false;
  let decoding = false;

  function placeholder(text) {
    ctx.fillStyle = "#111";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#ddd";
    ctx.font = "34px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  }

  function ensureCanvas() {
    if (canvas) return;
    canvas = document.createElement("canvas");
    canvas.width = 1280;
    canvas.height = 720;
    ctx = canvas.getContext("2d");
    placeholder("Waiting for the Snap Vanish app... press Start");
    // Keep the placeholder fresh while the app is not running.
    setInterval(() => {
      if (live && Date.now() - lastFrame > 2000) {
        live = false;
        placeholder("Snap Vanish app stopped - press Start");
      }
    }, 1000);
  }

  function base64ToBlob(b64) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: "image/jpeg" });
  }

  window.addEventListener("message", async (e) => {
    if (e.source !== window || !e.data || !e.data.__snapvanish_frame || !canvas) return;
    if (!e.data.ok) return;
    if (decoding) return; // drop frames rather than queueing latency
    decoding = true;
    try {
      const bmp = await createImageBitmap(base64ToBlob(e.data.jpeg));
      if (canvas.width !== bmp.width || canvas.height !== bmp.height) {
        canvas.width = bmp.width;
        canvas.height = bmp.height;
      }
      ctx.drawImage(bmp, 0, 0);
      bmp.close();
      live = true;
      lastFrame = Date.now();
    } catch (err) {
      /* ignore a corrupt frame */
    } finally {
      decoding = false;
    }
  });

  function makeTrack() {
    ensureCanvas();
    const track = canvas.captureStream(30).getVideoTracks()[0];
    if (++users === 1) window.postMessage({ __snapvanish_ctl: "start" }, "*");
    const stop = track.stop.bind(track);
    let stopped = false;
    track.stop = () => {
      if (!stopped) {
        stopped = true;
        if (--users === 0) window.postMessage({ __snapvanish_ctl: "stop" }, "*");
      }
      stop();
    };
    const getSettings = track.getSettings.bind(track);
    track.getSettings = () => ({ ...getSettings(), deviceId: DEVICE_ID, groupId: DEVICE_ID });
    Object.defineProperty(track, "label", { value: LABEL });
    return track;
  }

  function requestedIds(video) {
    if (!video || typeof video !== "object") return [];
    const id = video.deviceId;
    if (!id) return [];
    if (typeof id === "string") return [id];
    if (Array.isArray(id)) return id;
    const v = id.exact ?? id.ideal;
    return Array.isArray(v) ? v : v ? [v] : [];
  }

  function wantsSnapVanish(video) {
    if (!video) return false;
    const ids = requestedIds(video);
    // No specific camera requested -> Snap Vanish is the default camera.
    return ids.length === 0 || ids.includes(DEVICE_ID);
  }

  md.getUserMedia = async function (constraints) {
    if (constraints && wantsSnapVanish(constraints.video)) {
      const tracks = [makeTrack()];
      if (constraints.audio) {
        const audio = await origGetUserMedia({ audio: constraints.audio });
        tracks.push(...audio.getAudioTracks());
      }
      return new MediaStream(tracks);
    }
    return origGetUserMedia(constraints);
  };

  md.enumerateDevices = async function () {
    const devices = await origEnumerate();
    const fake = Object.create(MediaDeviceInfo.prototype, {
      deviceId: { value: DEVICE_ID, enumerable: true },
      groupId: { value: DEVICE_ID, enumerable: true },
      kind: { value: "videoinput", enumerable: true },
      label: { value: LABEL, enumerable: true },
      toJSON: { value: () => ({ deviceId: DEVICE_ID, groupId: DEVICE_ID, kind: "videoinput", label: LABEL }) },
    });
    return [fake, ...devices];
  };
})();
