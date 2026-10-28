"""Localhost-only HTTP frame server feeding the Snap Vanish browser extension.

This replaces a virtual-camera driver (which needs admin rights to install):
the extension fetches the latest processed JPEG from here and exposes it to
Google Meet as a camera. The server binds to 127.0.0.1 only, so nothing is
reachable from other machines.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DEFAULT_PORT = 8765

_TEST_PAGE = b"""<!doctype html><meta charset="utf-8"><title>Snap Vanish output</title>
<body style="margin:0;background:#111;color:#ccc;font-family:sans-serif">
<p style="padding:8px">This is exactly what Google Meet receives from Snap Vanish.</p>
<img id="v" style="max-width:100%">
<script>
let since = "";
async function loop() {
  try {
    const r = await fetch("/frame.jpg?since=" + since, {cache: "no-store"});
    if (r.status === 200) {
      since = r.headers.get("X-Frame-Id");
      const url = URL.createObjectURL(await r.blob());
      const img = document.getElementById("v"), old = img.src;
      img.src = url; if (old) URL.revokeObjectURL(old);
    }
  } catch (e) { await new Promise(res => setTimeout(res, 1000)); }
  setTimeout(loop, 0);
}
loop();
</script>"""


class FrameServer:
    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._jpeg: bytes | None = None
        self._id = 0
        self._cond = threading.Condition()
        self._last_request = 0.0
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        """True while a client fetched frames recently (skip JPEG encoding otherwise)."""
        return time.monotonic() - self._last_request < 2.0

    def publish(self, jpeg: bytes) -> None:
        with self._cond:
            self._jpeg = jpeg
            self._id += 1
            self._cond.notify_all()

    def next_frame(self, since: int, timeout: float = 0.2) -> tuple[int, bytes | None]:
        """Return a frame newer than ``since``, waiting briefly for one."""
        self._last_request = time.monotonic()
        with self._cond:
            self._cond.wait_for(lambda: self._id != since and self._jpeg is not None, timeout)
            if self._id == since:
                return self._id, None
            return self._id, self._jpeg

    def start(self) -> None:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def _cors(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Access-Control-Expose-Headers", "X-Frame-Id")
                self.send_header("Cache-Control", "no-store")

            def do_OPTIONS(self):
                self.send_response(204)
                self._cors()
                self.send_header("Access-Control-Allow-Methods", "GET")
                self.end_headers()

            def do_GET(self):
                url = urlparse(self.path)
                if url.path == "/frame.jpg":
                    try:
                        since = int(parse_qs(url.query).get("since", ["-1"])[0] or -1)
                    except ValueError:
                        since = -1
                    fid, jpeg = server.next_frame(since)
                    if jpeg is None:
                        self.send_response(204)
                        self._cors()
                        self.end_headers()
                        return
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(jpeg)))
                    self.send_header("X-Frame-Id", str(fid))
                    self.end_headers()
                    self.wfile.write(jpeg)
                elif url.path == "/status":
                    body = json.dumps({"app": "snap-vanish", "frame": server._id}).encode()
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
                elif url.path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(_TEST_PAGE)
                else:
                    self.send_error(404)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.port = self._httpd.server_address[1]
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="frame-server",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        with self._cond:
            self._cond.notify_all()
