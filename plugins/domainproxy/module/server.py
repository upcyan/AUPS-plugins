from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import proxy, service

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_HEAD(self): self._proxy()
    def do_GET(self): self._proxy()
    def _proxy(self):
        cfg = service.read_config(); prefix = cfg.get("prefix", "").strip("/")
        path = self.path.lstrip("/")
        if prefix:
            if not path.startswith(prefix + "/"): self.send_error(404); return
            path = path[len(prefix) + 1:]
        try:
            r = proxy.fetch(path, self.command, dict(self.headers)); self.send_response(r.status)
            for k, v in r.headers.items():
                if k.lower() in ("content-type", "content-length", "etag", "last-modified", "www-authenticate", "docker-content-digest", "accept-ranges"): self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                for chunk in iter(lambda: r.read(65536), b""): self.wfile.write(chunk)
        except Exception as e: self.send_error(400, str(e))
    def log_message(self, fmt, *args): pass

def main():
    cfg = service.read_config()
    ThreadingHTTPServer(("127.0.0.1", int(cfg.get("port", 18765))), Handler).serve_forever()
if __name__ == "__main__": main()
