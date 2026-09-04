from importlib import import_module
from ... import config, registry
from ...errors import AppError

def _provider(name):
    if name == "certmanager" or name not in registry.capability_providers("ssl"): raise AppError("SSL provider 不可用")
    return import_module(config.module_ref(f"modules.{name}.api"))

def providers(): return [n for n in registry.capability_providers("ssl") if n != "certmanager"]
def list_certs():
    out=[]
    for name in providers():
        fn=getattr(_provider(name),"list_certs",None)
        if callable(fn): out.extend(fn())
    return out
def request_cert(domain,email=None,provider=None):
    names=[provider] if provider else providers()
    if not names: raise AppError("未启用可用 SSL provider")
    return _provider(names[0]).request_cert(domain,email)
def find_cert(domain=None):
    for item in list_certs():
        if not domain or item["domain"]==domain: return item["cert"],item["key"]
    return None,None
def renew(provider=None):
    names=[provider] if provider else providers()
    return {"ok":True,"results":[_provider(n).renew() for n in names]}
def delete_cert(provider,domain): return _provider(provider).delete_cert(domain)
def status(): return {"installed":bool(providers()),"providers":providers(),"certificates":len(list_certs())}
