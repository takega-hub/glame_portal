#!/usr/bin/env python3
import http.client
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


BACKEND_HOST = "localhost"
BACKEND_PORT = 8000
PROXY_PREFIXES = ("/api", "/static", "/uploads")


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        exc_type, exc, _ = sys.exc_info()
        if exc_type in {ConnectionResetError, BrokenPipeError, TimeoutError}:
            return
        super().handle_error(request, client_address)


class StorefrontHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        default_dir = Path(__file__).resolve().parent
        static_dir = Path(os.environ.get("STOREFRONT_DIR", str(default_dir))).resolve()
        super().__init__(*args, directory=str(static_dir), **kwargs)

    def do_GET(self):
        self._handle()

    def do_HEAD(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    def do_PATCH(self):
        self._handle()

    def do_OPTIONS(self):
        self._handle()

    def _handle(self):
        path = urlsplit(self.path).path
        if path.startswith(PROXY_PREFIXES):
            self._proxy_request()
            return
        if self.command not in {"GET", "HEAD"}:
            self.send_error(405, "Method Not Allowed")
            return
        if path != "/" and not Path(self.directory, path.lstrip("/")).exists():
            self.path = "/index.html"
        if self.command == "HEAD":
            super().do_HEAD()
            return
        super().do_GET()

    def end_headers(self):
        # Prevent browser from serving stale Flutter bundles between rebuilds.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _proxy_request(self):
        body = None
        content_length = self.headers.get("Content-Length")
        if content_length:
            body = self.rfile.read(int(content_length))

        conn = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=60)
        headers = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in {"host", "connection", "accept-encoding", "content-length"}:
                continue
            headers[key] = value
        headers["Host"] = f"{BACKEND_HOST}:{BACKEND_PORT}"

        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()

            self.send_response(resp.status, resp.reason)
            for key, value in resp.getheaders():
                lower = key.lower()
                if lower in {"transfer-encoding", "connection", "content-length"}:
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            payload = f'{{"detail":"Proxy error: {str(exc)}"}}'.encode("utf-8")
            try:
                self.send_response(502, "Bad Gateway")
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                return
        finally:
            conn.close()


def main():
    port = int(os.environ.get("STOREFRONT_PORT", "9091"))
    server = QuietThreadingHTTPServer(("0.0.0.0", port), StorefrontHandler)
    static_dir = Path(os.environ.get("STOREFRONT_DIR", str(Path(__file__).resolve().parent))).resolve()
    print(f"Storefront server started on http://0.0.0.0:{port} from {static_dir} (proxying /api,/static,/uploads -> {BACKEND_HOST}:{BACKEND_PORT})")
    server.serve_forever()


if __name__ == "__main__":
    main()
