"""青·擎防火墙 provider：经公共契约复用 secgroup 的 nftables 引擎。"""

from ...core import contracts

PROVIDER = "secgroup"


def _call(api_id, **kwargs):
    return contracts.call("cyansecengine", PROVIDER, api_id, **kwargs)


def status():
    return _call("status")


def open_port(port, protocol="tcp", source=None, pwd=None):
    return _call("open_port", port=port, protocol=protocol, source=source, pwd=pwd)


def close_port(port, protocol="tcp", source=None, pwd=None):
    return _call("close_port", port=port, protocol=protocol, source=source, pwd=pwd)


def start():
    return _call("start")


def stop():
    return _call("stop")


remove = stop

__all__ = ["status", "open_port", "close_port", "start", "stop", "remove"]
