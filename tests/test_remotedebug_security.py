"""远程调试插件安全边界测试：只读命令白名单、根目录限制、输出脱敏、限时令牌。

每条断言对应一个真实可被利用的缺陷：
- 拒绝 shell 元字符（管道/重定向/命令连接）——否则只读白名单形同虚设；
- 拒绝目录外可执行文件与 PATH 劫持——否则等于任意命令执行；
- 文件参数归一后必须落在允许根内，含 ../ 穿越与符号链接逃逸；
- 旗标白名单，阻止 find -delete / tail -f / caddy fmt --overwrite 等写入或挂起；
- 输出脱敏，且不误伤 update.json 的 MD5/SHA-256 校验值；
- 令牌只存哈希，过期与吊销立即失效。

Isolated: 只用临时目录与标准只读工具，不起任何服务。
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = "remotedebug"


def _stub_modules():
    """构造插件相对导入所需的模块桩。"""
    mods = {}
    for name in ("review", "review.modules", "review.modules." + PLUGIN):
        mods[name] = types.ModuleType(name)
        mods[name].__path__ = []
    for name in ("config", "errors", "util"):
        mods["review." + name] = types.ModuleType("review." + name)
    mods["review.errors"].AppError = RuntimeError
    mods["review.config"].plugin_dir = lambda name, kind: os.path.join(
        tempfile.gettempdir(), "aups-remotedebug-stub", name, kind)
    for name in ("config", "errors", "util"):
        setattr(mods["review"], name, mods["review." + name])
    return mods


def _load(name):
    spec = importlib.util.spec_from_file_location(
        "review.modules.%s.%s" % (PLUGIN, name),
        ROOT / "plugins" / PLUGIN / "module" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Base(unittest.TestCase):
    def setUp(self):
        self._patcher = __import__("unittest.mock", fromlist=["patch"]).patch.dict(
            sys.modules, _stub_modules())
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)
        self.root = self.base / "opt/aups"
        (self.root / "config/caddy").mkdir(parents=True)
        (self.root / "data/remotedebug").mkdir(parents=True)
        (self.root / "config/caddy/Caddyfile").write_text(
            "update.050709.xyz {\n    root * /var/www/html\n}\n", encoding="utf-8")
        self.outside = self.base / "outside"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("TOPSECRET", encoding="utf-8")
        self.roots = [str(self.root)]
        self.third_party = []
        for name in ("redact", "runner", "store"):
            mod = _load(name)
            self.third_party.append(mod)
            setattr(self, name, mod)

    def cmd(self, line, **kw):
        kw.setdefault("roots", self.roots)
        return self.runner.execute(line, **kw)


class RedactTests(_Base):
    def test_redacts_key_value_secrets_but_keeps_keys(self):
        text = ("password=hunter2\n"
                "token: abc123\n"
                "api_key=xyz789\n"
                "db_pass = p@ss\n")
        out = self.redact.redact(text)
        for secret in ("hunter2", "abc123", "xyz789", "p@ss"):
            self.assertNotIn(secret, out)
        self.assertIn("password=", out)
        self.assertIn("token", out)

    def test_redacts_json_and_query_secrets(self):
        out = self.redact.redact(
            '{"token": "abc123", "user": "bob", "url": "https://h/p?access_key=k1&x=1"}')
        self.assertNotIn("abc123", out)
        self.assertNotIn("k1", out)
        self.assertIn("bob", out)

    def test_redacts_pem_bearer_and_url_userinfo(self):
        pem = ("-----BEGIN OPENSSH PRIVATE KEY-----\nAAAAb3JpZ2luYWw=\n"
               "-----END OPENSSH PRIVATE KEY-----")
        out = self.redact.redact(pem + "\nAuthorization: Bearer abc.def.ghi\n"
                                      "remote https://user:pw@host/repo.git")
        self.assertNotIn("AAAAb3JpZ2luYWw=", out)
        self.assertNotIn("abc.def.ghi", out)
        self.assertNotIn("user:pw@", out)

    def test_keeps_checksums_versioncodes_and_normal_logs(self):
        md5 = "d41d8cd98f00b204e9800998ecf8427e"
        sha = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        text = ('{"apkMd5": "%s", "apkSha256": "%s", "versionCode": 3,'
                ' "apkUrl": "https://update.050709.xyz/app/apk/a-1.0.apk"}\n'
                '2026-10-11 GET /app/latest 302\n' % (md5, sha))
        out = self.redact.redact(text)
        self.assertIn(md5, out)
        self.assertIn(sha, out)
        self.assertIn('"versionCode": 3', out)
        self.assertIn("/app/apk/a-1.0.apk", out)

    def test_supports_custom_patterns(self):
        out = self.redact.redact("internal-42", extra_patterns=[r"internal-\d+"])
        self.assertNotIn("internal-42", out)

    def test_reports_redaction_count(self):
        self.assertGreater(self.redact.count("token=abc\n"), 0)
        self.assertEqual(self.redact.count("versionCode=3\n"), 0)


class ExecRejectionTests(_Base):
    def test_rejects_shell_operators_outside_quotes(self):
        for line in ("ls /opt/aups ; rm -rf /",
                     "ls /opt/aups && cat /etc/passwd",
                     "cat /opt/aups/x | mail attacker",
                     "cat /opt/aups/x > /etc/passwd",
                     "ls `id`",
                     "ls $(id)"):
            with self.subTest(line=line):
                with self.assertRaises(RuntimeError):
                    self.runner.validate_line(line, roots=self.roots)

    def test_allows_regex_pipe_inside_quotes(self):
        """grep -E "a|b" 里的 | 是正则，不是管道，必须放行。"""
        plan = self.runner.validate_line('grep -E "root|html" '
                                              + str(self.root / "config/caddy/Caddyfile"),
                                              roots=self.roots)
        self.assertEqual(plan["bin"].rsplit("/", 1)[-1], "grep")

    def test_rejects_non_catalog_binaries(self):
        for line in ("rm -rf /opt/aups", "curl http://x", "bash -c id",
                     "python3 -c print(1)", "sh", "/bin/sh"):
            with self.subTest(line=line):
                with self.assertRaises(RuntimeError):
                    self.runner.validate_line(line, roots=self.roots)

    def test_rejects_write_capable_or_hanging_flags(self):
        cfg = str(self.root / "config/caddy/Caddyfile")
        for line in ("find /opt/aups -delete",
                     "tail -f " + cfg,
                     "caddy fmt --overwrite " + cfg,
                     "caddy fmt -w " + cfg,
                     "ls -Z " + str(self.root),
                     "find /opt/aups -exec rm {} ;"):
            with self.subTest(line=line):
                with self.assertRaises(RuntimeError):
                    self.runner.validate_line(line, roots=self.roots)

    def test_rejects_paths_outside_roots(self):
        for line in ("cat " + str(self.outside / "secret.txt"),
                     "cat /etc/hostname",
                     "ls /etc",
                     "grep -r TOPSECRET /"):
            with self.subTest(line=line):
                with self.assertRaises(RuntimeError):
                    self.runner.validate_line(line, roots=self.roots)

    def test_rejects_traversal(self):
        with self.assertRaises(RuntimeError):
            self.runner.validate_line("cat ../../outside/secret.txt",
                                           roots=self.roots, cwd=str(self.root))

    def test_rejects_symlink_escape(self):
        link = self.root / "escape"
        link.symlink_to(self.outside / "secret.txt")
        with self.assertRaises(RuntimeError):
            self.runner.validate_line("cat escape", roots=self.roots,
                                           cwd=str(self.root))
        with self.assertRaises(RuntimeError):
            self.runner.validate_line("cat " + str(link), roots=self.roots)

    def test_rejects_empty_and_too_many_steps(self):
        with self.assertRaises(RuntimeError):
            self.runner.execute("", roots=self.roots)
        with self.assertRaises(RuntimeError):
            self.runner.execute("\n".join(["ls " + str(self.root)] * 50),
                                     roots=self.roots, max_steps=5)

    def test_binary_resolution_ignores_hostile_path(self):
        """PATH 前置目录里的同名程序不得被采用（防 PATH 劫持）。"""
        evil = self.base / "evilbin"
        evil.mkdir()
        fake = evil / "cat"
        fake.write_text("#!/bin/sh\necho pwned\n")
        fake.chmod(0o755)
        old = os.environ.get("PATH", "")
        os.environ["PATH"] = str(evil) + os.pathsep + old
        self.addCleanup(lambda: os.environ.__setitem__("PATH", old))
        plan = self.runner.validate_line(
            "cat " + str(self.root / "config/caddy/Caddyfile"), roots=self.roots)
        self.assertNotEqual(os.path.realpath(plan["bin"]), os.path.realpath(str(fake)))


class ExecRunTests(_Base):
    def test_runs_allowed_read_command(self):
        out = self.cmd("cat " + str(self.root / "config/caddy/Caddyfile"))
        self.assertTrue(out["ok"], out)
        self.assertIn("update.050709.xyz", out["stdout"])
        self.assertEqual(out["exit_code"], 0)

    def test_redacts_secrets_in_output(self):
        (self.root / "config/caddy/apps.json").write_text(
            '{"ci_token": "supersecretvalue"}', encoding="utf-8")
        out = self.cmd("cat " + str(self.root / "config/caddy/apps.json"))
        self.assertNotIn("supersecretvalue", out["stdout"])
        self.assertGreaterEqual(out["redactions"], 1)

    def test_truncates_large_output(self):
        big = self.root / "config/caddy/big.log"
        big.write_text("x" * 4096, encoding="utf-8")
        out = self.cmd("cat " + str(big), max_output=512)
        self.assertTrue(out["truncated"])
        self.assertLessEqual(len(out["stdout"]), 512 + 128)

    def test_reports_failure_without_raising(self):
        out = self.cmd("cat " + str(self.root / "config/caddy/missing"))
        self.assertFalse(out["ok"])
        self.assertIn("missing", out["stderr"] + out["stdout"])

    def test_script_runs_each_line_and_keeps_order(self):
        script = "\n".join(["ls " + str(self.root / "config/caddy"),
                            "cat " + str(self.root / "config/caddy/Caddyfile")])
        out = self.runner.execute(script, roots=self.roots)
        self.assertTrue(out["ok"], out)
        self.assertEqual(len(out["steps"]), 2)
        self.assertIn("Caddyfile", out["steps"][0]["stdout"])
        self.assertIn("update.050709.xyz", out["steps"][1]["stdout"])

    def test_script_rejects_whole_batch_when_any_line_unsafe(self):
        script = "\n".join(["ls " + str(self.root), "cat /etc/hostname"])
        with self.assertRaises(RuntimeError):
            self.runner.execute(script, roots=self.roots)

    def test_catalog_is_read_only_and_describes_commands(self):
        cat = self.runner.catalog()
        self.assertIn("cat", cat)
        self.assertIn("systemctl", cat)
        self.assertTrue(cat["cat"]["description"])
        self.assertNotIn("rm", cat)

    def test_timeout_is_bounded(self):
        with self.assertRaises(RuntimeError):
            self.runner.execute("ls " + str(self.root), roots=self.roots,
                                     timeout=0)


class StoreTests(_Base):
    def setUp(self):
        super().setUp()
        self.data = str(self.root / "data/remotedebug")

    def test_create_returns_token_but_stores_only_hash(self):
        created = self.store.create_session(label="调试", ttl_seconds=600,
                                            base=self.data)
        token = created["token"]
        self.assertGreaterEqual(len(token), 32)
        raw = (pathlib.Path(self.data) / "sessions.json").read_text()
        self.assertNotIn(token, raw)
        self.assertIn(self.store.hash_token(token), raw)

    def test_verify_accepts_valid_token(self):
        token = self.store.create_session(label="a", ttl_seconds=600,
                                          base=self.data)["token"]
        session = self.store.verify_token(token, base=self.data)
        self.assertIsNotNone(session)
        self.assertEqual(session["label"], "a")

    def test_verify_rejects_unknown_and_empty_token(self):
        self.assertIsNone(self.store.verify_token("nope", base=self.data))
        self.assertIsNone(self.store.verify_token("", base=self.data))

    def test_expired_token_is_rejected(self):
        token = self.store.create_session(label="a", ttl_seconds=60,
                                          base=self.data)["token"]
        sid = self.store.list_sessions(base=self.data)[0]["sid"]
        self.store._set_expiry_for_test(sid, time.time() - 1, base=self.data)
        self.assertIsNone(self.store.verify_token(token, base=self.data))

    def test_revoked_token_is_rejected_immediately(self):
        token = self.store.create_session(label="a", ttl_seconds=600,
                                          base=self.data)["token"]
        sid = self.store.list_sessions(base=self.data)[0]["sid"]
        self.store.revoke_session(sid, base=self.data)
        self.assertIsNone(self.store.verify_token(token, base=self.data))

    def test_ttl_is_clamped_to_hard_bounds(self):
        low = self.store.create_session(label="low", ttl_seconds=1, base=self.data)
        high = self.store.create_session(label="high", ttl_seconds=10 ** 9,
                                         base=self.data)
        self.assertGreaterEqual(low["session"]["ttl_seconds"], self.store.MIN_TTL)
        self.assertLessEqual(high["session"]["ttl_seconds"], self.store.MAX_TTL)

    def test_audit_records_actions_without_secrets(self):
        token = self.store.create_session(label="a", ttl_seconds=600,
                                          base=self.data)["token"]
        session = self.store.verify_token(token, base=self.data)
        self.store.record_audit(session, command="cat x", ok=True, exit_code=0,
                                duration_ms=5, output_bytes=10, ip="1.2.3.4",
                                base=self.data)
        rows = self.store.audit_log(base=self.data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["command"], "cat x")
        self.assertNotIn(token, json.dumps(rows))

    def test_session_can_restrict_roots_and_commands(self):
        created = self.store.create_session(
            label="narrow", ttl_seconds=600, roots=["/opt/aups"],
            commands=["cat"], base=self.data)
        self.assertEqual(created["session"]["roots"], ["/opt/aups"])
        self.assertEqual(created["session"]["commands"], ["cat"])


if __name__ == "__main__":
    unittest.main()
