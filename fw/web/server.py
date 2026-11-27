"""The HTTP handler: refuses what isn't this machine's page, answers from the route table (api.ROUTES)."""
from __future__ import annotations

import json
import mimetypes
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fw import store
from fw.web import api, live
from fw.web.current import ACTIVE, ACTIVE_LOCK


def refusal(method: str, path: str, host: str | None, origin: str | None, ctype: str | None, port: int) -> str | None:
    """Why a request isn't the page's own (None: it is): Host and any Origin must be 127.0.0.1:<port> or
    localhost:<port>; a PUT or POST must be JSON (a dropped picture's bytes, POST /api/picture, image/*). Pure."""
    ours = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if (host or "").strip().lower() not in ours:
        return "not this machine's page (Host)"
    if origin is not None and origin.strip().lower() not in {f"http://{h}" for h in ours}:
        return "not this machine's page (Origin)"
    if method in ("PUT", "POST"):
        kind = (ctype or "").split(";")[0].strip().lower()
        if kind != "application/json" and not (path == "/api/picture" and kind.startswith("image/")):
            return "expected Content-Type: application/json"
    return None


def active(n: int) -> None:
    with ACTIVE_LOCK:
        ACTIVE[0] += n


class Handler(BaseHTTPRequestHandler):
    groups: tuple = ()

    def do_GET(self):
        self.answer("GET")

    def do_PUT(self):
        self.answer("PUT")

    def do_POST(self):
        self.answer("POST")

    def answer(self, method: str):
        url = urlparse(self.path)
        why = refusal(method, url.path, self.headers.get("Host"), self.headers.get("Origin"),
                      self.headers.get("Content-Type"), self.server.server_address[1])
        if why:
            return self.send(403, {"error": why})
        self.query = parse_qs(url.query)
        fn, self.groups = api.route(method, url.path)
        try:
            got = fn(self) if fn else (404, {"error": "not found"})
        except store.StoreError as e:
            got = (500 if method == "GET" else 409), {"error": str(e)}
        except (OSError, ValueError) as e:
            got = 500, {"error": str(e)}
        if got:
            self.send(*got)

    def ask(self, name: str, default: str = "") -> str:
        return (self.query.get(name) or [default])[0]

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        got = json.loads(self.rfile.read(n).decode() or "{}") if n else {}
        if not isinstance(got, dict):
            raise ValueError("expected a JSON object")
        return got

    def send(self, code: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def file(self, path: Path):
        try:
            data = path.read_bytes()
        except OSError:
            return 404, {"error": "not found"}
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if path.suffix in (".html", ".js", ".css") else "max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def live(self):
        """GET /api/live: a page following isn't a request being answered, so a restart doesn't wait for it."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        active(-1)
        try:
            live.stream(lambda data: (self.wfile.write(data), self.wfile.flush()))
        finally:
            active(1)

    def log_message(self, *args):
        pass

    def handle(self):
        active(1)
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):   # the page went away mid-answer
            pass
        finally:
            active(-1)


class Server(ThreadingHTTPServer):
    def server_bind(self):   # (without HTTPServer's name lookup, which a slow resolver stalls for half a minute)
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def serve(port: int = 0) -> ThreadingHTTPServer:
    """The server on 127.0.0.1:`port` (0: any free one), running in a thread."""
    httpd = Server(("127.0.0.1", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
