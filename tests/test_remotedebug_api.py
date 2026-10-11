"""remotedebug API 路由层测试（直接调用真实处理函数，只隔离 FastAPI 注册）。

覆盖点（每条对应一个可被利用的缺陷）：
- 令牌面鉴权：缺失/错误/过期/已吊销 → 401；非 root → 403；
- 会话范围在 API 层生效：越出 commands 或 roots 的命令 → 干净拒绝；
- 审计：成功与失败都留痕，且不含令牌本身；
- 建会话：未知命令 / 不存在的目录拒绝，TTL 夹紧，空范围回落默认；
- 响应体不泄露令牌与哈希；
- 客户端可控的数值参数（max_steps/timeout/max_output）非数值时必须
  报「干净的 400」，而不是 ValueError/TypeError（否则单个请求即 500）。

Isolated: 只用临时目录与标准只读工具，不起任何服务。
"""
import json
import os
import pathlib
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_remotedebug_security import _stub_modules, _load  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = "remotedebug"


class _FakeHTTPException(Exception):
    """替代 fastapi.HTTPException：同时保留 status_code 与 detail。"""

    def __init__(self, status_code=None, detail=None, **kw):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class _FakeRouter:
    """替代 fastapi.APIRouter：记录路由并原样返回处理函数。"""

    def __init__(self):
        self.routes = []

    def _deco(self, method):
        def deco(path, **kw):
            def wrap(fn):
                self.routes.append((method, path, fn))
                return fn
            return wrap
        return deco

    def get(self, path, **kw):
        return self._deco("GET")(path)

    def post(self, path, **kw):
        return self._deco("POST")(path)

    def delete(self, path, **kw):
        return self._deco("DELETE")(path)


class _Req:
    """最小请求替身：仅提供路由实际读取的 headers / client.host。"""

    def __init__(self, headers=None, ip="127.0.0.1"):
        self.headers = dict(headers or {})
        self.client = types.SimpleNamespace(host=ip)


def _stub_api_modules(base_dir):
    """在只读模块桩之上补 FastAPI 与 websec 桩。"""
    mods = _stub_modules()
    mods["review.web"] = types.ModuleType("review.web")
    mods["review.web"].__path__ = []
    websec = types.ModuleType("review.web.websec")
    websec.require_auth = lambda *a, **k: True
    mods["review.web.websec"] = websec
    setattr(mods["review"], "web", mods["review.web"])
    setattr(mods["review.web"], "websec", websec)

    fastapi = types.ModuleType("fastapi")
    fastapi.APIRouter = _FakeRouter
    fastapi.Depends = lambda dep=None, **k: dep
    fastapi.HTTPException = _FakeHTTPException
    fastapi.Request = _Req
    fastapi.Body = lambda *a, **k: None
    fastapi.Query = lambda *a, **k: None
    mods["fastapi"] = fastapi

    mods["review.config"].plugin_dir = lambda name, kind: os.path.join(
        str(base_dir), name, kind)
    mods["review.util"].print_json = lambda *a, **k: None
    return mods


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)
        self.panel = self.base / "panel"
        self.root = self.panel / "opt/aups"
        (self.root / "config/caddy").mkdir(parents=True)
        (self.root / "data/remotedebug").mkdir(parents=True)
        self.cfg = self.root / "config/caddy/Caddyfile"
        self.cfg.write_text("update.050709.xyz {\n    root * /var/www/html\n}\n",
                            encoding="utf-8")
        self.secret = self.root / "config/caddy/apps.json"
        self.secret.write_text('{"ci_token":"SUPERSECRET123"}', encoding="utf-8")
        self.outside = self.base / "outside"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("OUTSIDE", encoding="utf-8")
        self.roots = [str(self.root)]

        mods = _stub_api_modules(self.panel)
        self.patch = patch.dict(sys.modules, mods)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        # 面板以 root 运行为正常态；默认模拟 root，仅在专门用例里降权。
        self.euid = patch("os.geteuid", return_value=0)
        self.euid.start()
        self.addCleanup(self.euid.stop)
        # 默认目录走环境变量注入，避免测试依赖宿主真实存在 /opt/aups
        self.env = patch.dict(os.environ,
                              {"AUP_REMOTEDEBUG_ROOTS": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        # 加载顺序：runner 依赖 redact，api 依赖 runner/store
        self.redact = _load("redact")
        self.runner = _load("runner")
        self.store = _load("store")
        self.api = _load("api")

    # ---------- 辅助 ----------

    def data_dir(self):
        return str(self.panel / "remotedebug" / "data")

    def open_session(self, **kw):
        kw.setdefault("label", "排障")
        kw.setdefault("ttl_seconds", 900)
        kw.setdefault("roots", self.roots)
        return self.store.create_session(base=self.data_dir(), **kw)

    def exec_call(self, command, token=None, headers=None, body_extra=None,
                  ip="203.0.113.7", expect_ok=True):
        body = {"command": command}
        if token is not None:
            body["token"] = token
        body.update(body_extra or {})
        req = _Req(headers=headers or {}, ip=ip)
        return self.api.rd_exec(req, body)

    # ---------- 令牌面鉴权 ----------

    def test_exec_requires_valid_token(self):
        """缺失/错误令牌必须 401，且绝不能真正执行命令。

        仅断言「抛异常」不够：变异实验表明，若鉴权被绕过，请求会因后续
        路径/参数校验同样抛异常而被误判为通过。故这里同时断言状态码为 401
        且审计中不存在任何成功记录（即命令确实没有执行）。
        """
        marker = self.root / "config/caddy/EXECUTED_MARKER"
        for token in (None, "", "wrong-token"):
            with self.subTest(token=token):
                with self.assertRaises(_FakeHTTPException) as ctx:
                    self.exec_call("cat " + str(self.cfg), token=token)
                self.assertEqual(ctx.exception.status_code, 401,
                                 "非 401 说明鉴权被绕过（执行流走到了后续校验）")
        self.assertFalse(marker.exists())
        # 未授权请求不应产生「成功执行」的审计
        rows = self.store.audit_log(base=self.data_dir())
        self.assertFalse([r for r in rows if r["ok"]],
                         "未授权请求不应有成功执行的审计记录")

    def test_exec_accepts_token_from_header(self):
        token = self.open_session()["token"]
        result = self.exec_call("cat " + str(self.cfg), token=None,
                                headers={"X-Debug-Token": token})
        self.assertTrue(result["ok"], result)
        self.assertIn("update.050709.xyz", result["stdout"])

    def test_exec_rejects_expired_token(self):
        created = self.open_session(ttl_seconds=60)
        sid = created["session"]["sid"]
        self.store._set_expiry_for_test(sid, time.time() - 5, base=self.data_dir())
        with self.assertRaises(_FakeHTTPException) as ctx:
            self.exec_call("ls " + str(self.root), token=created["token"])
        self.assertEqual(ctx.exception.status_code, 401)

    def test_exec_rejects_revoked_token(self):
        created = self.open_session()
        self.store.revoke_session(created["session"]["sid"], base=self.data_dir())
        with self.assertRaises(_FakeHTTPException) as ctx:
            self.exec_call("ls " + str(self.root), token=created["token"])
        self.assertEqual(ctx.exception.status_code, 401)

    def test_exec_requires_root(self):
        token = self.open_session()["token"]
        with patch("os.geteuid", return_value=1000):
            with self.assertRaises(_FakeHTTPException) as ctx:
                self.exec_call("ls " + str(self.root), token=token)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_no_token_cannot_read_any_file(self):
        """行为级断言：无令牌时读文件必须看不到内容（不依赖异常类型）。

        这是对鉴权绕过最直接的检验——即使异常类型/状态码被改动，只要内容
        泄露就说明鉴权失效。
        """
        leaked = False
        try:
            result = self.exec_call("cat " + str(self.cfg), token=None)
            leaked = "update.050709.xyz" in json.dumps(result, ensure_ascii=False)
        except _FakeHTTPException as e:
            leaked = e.status_code != 401
        self.assertFalse(leaked, "无令牌请求读到了文件内容 → 鉴权被绕过")

    # ---------- 会话范围（API 层必须生效） ----------

    def test_session_command_limit_enforced(self):
        token = self.open_session(commands=["cat"])["token"]
        ok = self.exec_call("cat " + str(self.cfg), token=token)
        self.assertIn("update.050709.xyz", ok["stdout"])
        with self.assertRaises(_FakeHTTPException) as ctx:
            self.exec_call("ls " + str(self.root), token=token)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_session_root_limit_enforced(self):
        """会话限定的目录必须真正生效：既不能越界读取，也不能放宽到默认集合。

        仅断言「被拒绝」不够——若实现忽略会话 roots 而改用默认集合，越界请求
        同样会被拒绝（恰好的巧合），测试就会漏掉范围失效。故同时断言：
        会话内允许的路径可读，且拒绝理由确实来自会话范围。
        """
        scope = self.root / "config"
        token = self.open_session(roots=[str(scope)])["token"]
        # 会话范围内：可读
        ok = self.exec_call("cat " + str(self.cfg), token=token)
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(ok["roots"], [str(scope)],
                         "响应 roots 必须是会话限定值，而非服务端默认集合")
        # 会话范围外：拒绝
        with self.assertRaises(_FakeHTTPException) as ctx:
            self.exec_call("cat " + str(self.outside / "secret.txt"), token=token)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_session_root_scope_not_widened_to_defaults(self):
        """会话限定子目录时，默认集合里的其他目录也不得可读。"""
        scope = self.root / "config"
        other = self.root / "data/remotedebug"
        (other / "note.txt").write_text("DEFAULT-AREA", encoding="utf-8")
        token = self.open_session(roots=[str(scope)])["token"]
        with self.assertRaises(_FakeHTTPException) as ctx:
            self.exec_call("cat " + str(other / "note.txt"), token=token)
        self.assertEqual(ctx.exception.status_code, 400,
                         "会话限定的目录范围被放宽到了默认集合")

    def test_empty_session_scope_falls_back_to_defaults(self):
        """会话未限定 roots/commands 时，回落到服务端默认目录与全部只读命令。"""
        token = self.open_session(commands=[], roots=[])["token"]
        result = self.exec_call("cat " + str(self.cfg), token=token)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["roots"], [str(self.root)])

    # ---------- 输出与审计 ----------

    def test_exec_output_is_redacted(self):
        token = self.open_session()["token"]
        result = self.exec_call("cat " + str(self.secret), token=token)
        self.assertNotIn("SUPERSECRET123", json.dumps(result, ensure_ascii=False))
        self.assertGreaterEqual(result["redactions"], 1)

    def test_exec_records_audit_for_success_and_failure(self):
        token = self.open_session()["token"]
        self.exec_call("cat " + str(self.cfg), token=token, ip="198.51.100.5")
        with self.assertRaises(_FakeHTTPException):
            self.exec_call("cat /etc/hostname", token=token, ip="198.51.100.5")
        rows = self.store.audit_log(base=self.data_dir())
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(r["ok"] for r in rows))
        self.assertTrue(any(not r["ok"] for r in rows))
        self.assertTrue(all(r["ip"] == "198.51.100.5" for r in rows))

    def test_audit_never_contains_token(self):
        created = self.open_session()
        token = created["token"]
        self.exec_call("cat " + str(self.cfg), token=token)
        blob = json.dumps(self.store.audit_log(base=self.data_dir()),
                          ensure_ascii=False)
        self.assertNotIn(token, blob)
        self.assertNotIn(self.store.hash_token(token), blob)

    def test_response_never_leaks_token_or_hash(self):
        created = self.open_session()
        token = created["token"]
        result = self.exec_call("cat " + str(self.cfg), token=token)
        blob = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(token, blob)
        self.assertNotIn(self.store.hash_token(token), blob)

    # ---------- 客户端可控数值参数（不能 500） ----------

    def test_non_numeric_limits_rejected_cleanly(self):
        token = self.open_session()["token"]
        for field, value in (("max_steps", "abc"), ("timeout", "abc"),
                             ("max_output", "abc"), ("timeout", 0),
                             ("max_output", -5), ("max_steps", 9999)):
            with self.subTest(field=field, value=value):
                with self.assertRaises(_FakeHTTPException) as ctx:
                    self.exec_call("cat " + str(self.cfg), token=token,
                                   body_extra={field: value})
                self.assertEqual(ctx.exception.status_code, 400,
                                 "非法参数必须干净拒绝，而不是 500")

    def test_explicit_null_limits_mean_use_default(self):
        """JSON null 等价于省略：沿用服务端默认，不得 500 也不得静默越界。"""
        token = self.open_session()["token"]
        for field in ("max_steps", "timeout", "max_output"):
            with self.subTest(field=field):
                result = self.exec_call("cat " + str(self.cfg), token=token,
                                        body_extra={field: None})
                self.assertTrue(result["ok"], result)

    def test_out_of_range_limits_rejected_cleanly(self):
        token = self.open_session()["token"]
        for field, value in (("timeout", 0), ("timeout", -1), ("timeout", 99999),
                             ("max_steps", 0), ("max_steps", 9999),
                             ("max_output", 0), ("max_output", -5)):
            with self.subTest(field=field, value=value):
                with self.assertRaises(_FakeHTTPException) as ctx:
                    self.exec_call("cat " + str(self.cfg), token=token,
                                   body_extra={field: value})
                self.assertEqual(ctx.exception.status_code, 400)

    # ---------- 建会话 ----------

    def test_create_session_rejects_unknown_command(self):
        with self.assertRaises(RuntimeError):
            self.api.rd_create({"commands": ["rm"], "ttl_seconds": 600})

    def test_create_session_rejects_missing_root(self):
        with self.assertRaises(RuntimeError):
            self.api.rd_create({"roots": [str(self.base / "nope")]})

    def test_create_session_clamps_ttl_and_returns_token_once(self):
        low = self.api.rd_create({"ttl_seconds": 1, "roots": self.roots})
        high = self.api.rd_create({"ttl_seconds": 10 ** 9, "roots": self.roots})
        self.assertGreaterEqual(low["session"]["ttl_seconds"], self.store.MIN_TTL)
        self.assertLessEqual(high["session"]["ttl_seconds"], self.store.MAX_TTL)
        self.assertTrue(low["token"])
        raw = (pathlib.Path(self.data_dir()) / "sessions.json").read_text()
        self.assertNotIn(low["token"], raw)

    def test_create_session_defaults_roots_when_empty(self):
        created = self.api.rd_create({"label": "x"})
        self.assertEqual(created["session"]["roots"], [str(self.root)])

    # ---------- 管理与只读接口 ----------

    def test_revoke_endpoints(self):
        a = self.open_session()
        b = self.open_session()
        self.api.rd_revoke(a["session"]["sid"])
        self.assertIsNone(self.store.verify_token(a["token"], base=self.data_dir()))
        self.assertIsNotNone(self.store.verify_token(b["token"], base=self.data_dir()))
        self.api.rd_revoke_all()
        self.assertIsNone(self.store.verify_token(b["token"], base=self.data_dir()))

    def test_status_is_read_only_and_interactive_deferred(self):
        st = self.api.rd_status()
        self.assertEqual(st["mode"], "read-only")
        self.assertFalse(st["interactive"]["enabled"])
        self.assertIn("catalog", st)
        self.assertNotIn("rm", st["catalog"])
        self.assertEqual(st["sessions"], 0)

    def test_sessions_and_audit_endpoints(self):
        created = self.open_session()
        listed = self.api.rd_sessions()["sessions"]
        self.assertEqual([s["sid"] for s in listed], [created["session"]["sid"]])
        self.assertNotIn("token_hash", json.dumps(listed))
        self.exec_call("cat " + str(self.cfg), token=created["token"])
        self.assertEqual(len(self.api.rd_audit()["audit"]), 1)

    def test_catalog_endpoint_lists_read_only_commands(self):
        cat = self.api.rd_catalog()["catalog"]
        for name in ("cat", "ls", "grep", "caddy", "systemctl"):
            self.assertIn(name, cat)
            self.assertNotIn("-delete", " ".join(cat[name]["flags"]))

    def test_all_routes_registered_on_expected_paths(self):
        paths = {(m, p) for m, p, _ in self.api.router.routes}
        for expected in (("POST", "/remotedebug/exec"),
                         ("POST", "/remotedebug/run"),
                         ("GET", "/remotedebug/status"),
                         ("GET", "/remotedebug/sessions"),
                         ("POST", "/remotedebug/sessions"),
                         ("POST", "/remotedebug/revoke-all"),
                         ("GET", "/remotedebug/audit"),
                         ("GET", "/remotedebug/catalog")):
            self.assertIn(expected, paths)

    # ---------- 面板页面执行入口（/run，面板会话鉴权） ----------

    def test_run_endpoint_does_not_require_debug_token(self):
        """页面执行按钮走 /run：面板登录态即可，不该索要调试令牌。

        回归背景：前端曾调用令牌面 /exec 且不带令牌，页面「执行」必然 401。
        """
        result = self.api.rd_run(_Req(ip="198.51.100.9"),
                                 {"command": "cat " + str(self.cfg)})
        self.assertTrue(result["ok"], result)
        self.assertIn("update.050709.xyz", result["stdout"])

    def test_run_still_restricted_to_read_only_catalog(self):
        for line in ("rm -rf " + str(self.root), "cat /etc/hostname",
                     "cat " + str(self.outside / "secret.txt")):
            with self.subTest(line=line):
                with self.assertRaises(_FakeHTTPException) as ctx:
                    self.api.rd_run(_Req(), {"command": line})
                self.assertEqual(ctx.exception.status_code, 400)

    def test_run_output_is_redacted_and_audited(self):
        result = self.api.rd_run(_Req(ip="198.51.100.9"),
                                 {"command": "cat " + str(self.secret)})
        self.assertNotIn("SUPERSECRET123", json.dumps(result, ensure_ascii=False))
        rows = self.store.audit_log(base=self.data_dir())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["ok"])
        self.assertEqual(rows[0]["ip"], "198.51.100.9")

    def test_frontend_uses_run_not_exec(self):
        """静态检查：页面执行必须调 /run，否则线上又会 401。"""
        source = (ROOT / "plugins" / PLUGIN / "frontend.js").read_text(encoding="utf-8")
        code = "\n".join(l for l in source.splitlines()
                         if not l.strip().startswith(("//", "*", "/*")))
        self.assertIn("/api/remotedebug/run", code)
        self.assertNotIn("api('POST', '/api/remotedebug/exec'", code)

    def test_token_endpoint_still_requires_token(self):
        """令牌面不受影响：没有令牌仍必须 401。"""
        with self.assertRaises(_FakeHTTPException) as ctx:
            self.exec_call("cat " + str(self.cfg), token=None)
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
