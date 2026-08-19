"""Static file server for local testing that never lets the browser cache
anything. Plain `python -m http.server` leaves heuristic HTTP caching in place,
which has repeatedly served stale JS during development (separate from, and in
addition to, the app's own service worker cache). Dev-only — not part of the
shipping app, GitHub Pages serves the real thing.

Run: ./.venv/Scripts/python.exe tools/devserver.py [port]
"""

import sys
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # quiet — avoid drowning the console in per-file GET lines


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
    root = Path(__file__).resolve().parent.parent
    handler = lambda *args: NoCacheHandler(*args, directory=str(root))
    print(f"serving {root} on http://localhost:{port} (no-cache)")
    # Threading, not the plain single-threaded HTTPServer: Chrome opens several
    # concurrent connections per page load (JS/CSS in parallel, plus keep-alive),
    # and a synchronous server queues them up badly enough that some requests
    # appear to the browser as connection failures.
    ThreadingHTTPServer(("", port), handler).serve_forever()
