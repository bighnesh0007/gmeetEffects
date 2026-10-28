import threading
import urllib.request

from gmeet_effects.stream_server import FrameServer


def test_serves_latest_frame_and_long_polls():
    srv = FrameServer(port=0)
    srv.start()
    port = srv._httpd.server_address[1]
    try:
        srv.publish(b"jpeg-1")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/frame.jpg") as r:
            fid = r.headers["X-Frame-Id"]
            assert r.read() == b"jpeg-1"
            assert r.headers["Access-Control-Allow-Origin"] == "*"
        assert srv.active

        # Same id again -> 204 after a short wait (no new frame).
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/frame.jpg?since={fid}") as r:
            assert r.status == 204

        # A frame published while the client waits is returned immediately.
        threading.Timer(0.05, srv.publish, args=(b"jpeg-2",)).start()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/frame.jpg?since={fid}") as r:
            assert r.read() == b"jpeg-2"
    finally:
        srv.stop()
