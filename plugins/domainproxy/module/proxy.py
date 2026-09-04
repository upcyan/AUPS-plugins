import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from ...errors import AppError

ALLOWED = ("github.com", "api.github.com", "raw.githubusercontent.com", "objects.githubusercontent.com", "codeload.github.com", "registry-1.docker.io", "auth.docker.io", "production.cloudflare.docker.com")

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _validate(raw):
    url = urllib.parse.unquote(raw or "")
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
        raise AppError("仅允许 http/https 的 GitHub 或 Docker Registry 地址")
    host = p.hostname.lower().rstrip(".")
    if host not in ALLOWED:
        raise AppError("目标域名不在 GitHub/Docker 允许列表")
    try:
        ipaddress.ip_address(host)
        raise AppError("不允许 IP 地址目标")
    except ValueError:
        pass
    for item in socket.getaddrinfo(host, 443 if p.scheme == "https" else 80, type=socket.SOCK_STREAM):
        addr = ipaddress.ip_address(item[4][0])
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            raise AppError("目标解析到非公网地址，已拒绝")
    return url, host

def fetch(raw, method="GET", headers=None, _depth=0, _origin=None):
    url, host = _validate(raw)
    safe = {"User-Agent": "AUPS-domainproxy/1.0", "Host": host}
    for k, v in (headers or {}).items():
        if k.lower() in ("accept", "range") or (k.lower() == "authorization" and (_origin is None or _origin == host)):
            safe[k] = v
    try:
        return urllib.request.build_opener(_NoRedirect()).open(urllib.request.Request(url, headers=safe, method=method), timeout=45)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
            if _depth >= 5: raise AppError("上游重定向次数过多")
            target = urllib.parse.urljoin(url, e.headers["Location"])
            return fetch(target, method, headers, _depth + 1, _origin or host)
        return e
