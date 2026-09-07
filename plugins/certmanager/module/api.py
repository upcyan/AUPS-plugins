from importlib import import_module
from pathlib import Path
import ssl
import time
import math
from ...core import ssl as ssl_core
from ... import config, registry
from ...errors import AppError

def _provider(name):
    if name == "certmanager" or name not in registry.capability_providers("ssl"): raise AppError("SSL provider 不可用")
    return import_module(config.module_ref(f"modules.{name}.api"))

def providers(): return [n for n in registry.capability_providers("ssl") if n != "certmanager"]
def list_certs():
    out, seen = [], set()
    for name in providers():
        fn = getattr(_provider(name), "list_certs", None)
        if callable(fn):
            for cert in fn():
                marker = str(Path(cert["cert"]).resolve())
                if marker not in seen:
                    seen.add(marker)
                    out.append({**cert, "provider": name, "managed": True})
    # Filesystem discovery also includes certificates owned by reverse proxies.
    # Do not delegate mutation of these files to an unrelated SSL provider.
    for cert in ssl_core.list_certs():
        marker = str(Path(cert["cert"]).resolve())
        if marker not in seen:
            seen.add(marker)
            out.append({**cert, "provider": None, "managed": False})
    for cert in out:
        cert.update(issued_at=None, expires_at=None, remaining_days=None)
        try:
            metadata = ssl._ssl._test_decode_cert(cert["cert"])
            issued = ssl.cert_time_to_seconds(metadata["notBefore"])
            expires = ssl.cert_time_to_seconds(metadata["notAfter"])
            cert.update(issued_at=issued, expires_at=expires,
                        remaining_days=math.floor((expires - time.time()) / 86400))
        except (OSError, ValueError, KeyError, AttributeError):
            cert["validity_error"] = "无法读取证书有效期"
    return out

def request_cert(domain,email=None,provider=None):
    names=[provider] if provider else providers()
    if not names: raise AppError("未启用可用 SSL provider")
    return _provider(names[0]).request_cert(domain,email)
def find_cert(domain=None):
    for item in list_certs():
        if not domain or item["domain"]==domain: return item["cert"],item["key"]
    return None,None
def renew(provider=None,domain=None):
    names=[provider] if provider else providers()
    results=[]
    for n in names:
        mod=_provider(n); fn=getattr(mod,"renew_cert",None) if domain else None
        results.append(fn(domain) if callable(fn) else mod.renew())
    return {"ok":True,"results":results}
def update_cert(provider,domain,email=None):
    mod=_provider(provider); fn=getattr(mod,"renew_cert",None)
    return fn(domain) if callable(fn) else mod.request_cert(domain,email)
def delete_cert(provider,domain): return _provider(provider).delete_cert(domain)
def status(): return {"installed":bool(providers()),"providers":providers(),"certificates":len(list_certs())}
