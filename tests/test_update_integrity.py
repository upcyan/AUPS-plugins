"""update.json 双校验：真实临时文件、固定摘要与同步调用链回归。"""
import ast
import json
import os
import pathlib
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from test_download_routes import _stub_modules, _load

MD5 = "900150983cd24fb0d6963f7d28e17f72"
SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


class UpdateIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name) / "demo"
        (self.base / "apk").mkdir(parents=True)
        (self.base / "apk/demo-1.0.apk").write_bytes(b"abc")
        # 日期更新的其他 APK 不可替代 apkUrl 指定的目标。
        (self.base / "apk/demo-2.0.apk").write_bytes(b"newer-and-different")
        self.path = self.base / "update.json"
        self.meta = {"versionName": "1.0", "versionCode": 1,
                     "apkUrl": "https://update.example.com/demo/apk/demo-1.0.apk",
                     "note": "保留日志", "changelogs": [{"versionName": "1.0", "note": "旧日志"}],
                     "custom": {"keep": True}}
        self.write_meta()
        modules = _stub_modules("appupdate")
        registry = pathlib.Path(self.tmp.name) / "apps.json"
        registry.write_text(json.dumps({"apps": {"demo": {"dir": str(self.base),
                            "deploy": {"domain": "update.example.com"}}}}))
        modules["review.config"].APPS_FILE = str(registry)
        self.modules = modules
        self.patcher = patch.dict(sys.modules, modules)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.apps = _load("appupdate", "apps")

    def write_meta(self):
        self.path.write_text(json.dumps(self.meta, ensure_ascii=False), encoding="utf-8")

    def call(self, write=False):
        fn = getattr(self.apps, "update_integrity", None)
        self.assertTrue(callable(fn), "缺少 update.json 双校验处理")
        return fn("demo", write=write)

    def test_fill_both_hashes_for_exact_url_and_preserve_other_fields(self):
        self.path.chmod(0o644)
        result = self.call(write=True)
        data = json.loads(self.path.read_text())
        self.assertEqual(data["apkMd5"], MD5)
        self.assertEqual(data["apkSha256"], SHA256)
        for key, value in self.meta.items():
            self.assertEqual(data[key], value)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["file"], "apk/demo-1.0.apk")
        self.assertTrue(result["updated"])
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o644)

    def test_status_reads_without_writing_and_reports_mismatch(self):
        self.meta.update(apkMd5="0" * 32, apkSha256=SHA256)
        self.write_meta()
        before = self.path.read_bytes()
        result = self.call()
        self.assertEqual(result["status"], "mismatch")
        self.assertFalse(result["md5_matches"])
        self.assertTrue(result["sha256_matches"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_correct_hashes_do_not_rewrite_metadata(self):
        self.meta.update(apkMd5=MD5, apkSha256=SHA256)
        self.write_meta()
        before = (self.path.read_bytes(), self.path.stat().st_mtime_ns)
        result = self.call(write=True)
        self.assertFalse(result["updated"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)

    def test_missing_target_never_uses_newer_apk(self):
        (self.base / "apk/demo-1.0.apk").unlink()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "不存在"):
            self.call(write=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_reject_traversal_foreign_app_foreign_host_and_shortlink(self):
        for url in ("https://update.example.com/demo/%2e%2e/out.apk",
                    "https://update.example.com/other/apk/demo-1.0.apk",
                    "https://evil.example.com/demo/apk/demo-1.0.apk",
                    "https://update.example.com/demo/latest",
                    "file:///etc/test.apk", "//evil.example.com/demo.apk"):
            with self.subTest(url=url):
                self.meta["apkUrl"] = url
                self.write_meta()
                before = self.path.read_bytes()
                with self.assertRaises(RuntimeError):
                    self.call(write=True)
                self.assertEqual(self.path.read_bytes(), before)

    def test_reject_symlink_target_outside_app(self):
        outside = pathlib.Path(self.tmp.name) / "outside.apk"
        outside.write_bytes(b"outside")
        target = self.base / "apk/demo-1.0.apk"
        target.unlink()
        target.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, "路径"):
            self.call(write=True)

    def test_relative_app_root_and_query_urls(self):
        for url in ("apk/demo-1.0.apk", "/apk/demo-1.0.apk",
                    "/demo/apk/demo-1.0.apk?download=1",
                    "https://update.example.com/demo/apk/demo-1.0.apk?token=x#fragment"):
            with self.subTest(url=url):
                self.meta["apkUrl"] = url
                self.write_meta()
                self.assertEqual(self.call()["file"], "apk/demo-1.0.apk")

    def test_absent_update_json_is_skipped_without_creating_one(self):
        self.path.unlink()
        self.assertEqual(self.call(write=True)["status"], "unavailable")
        self.assertFalse(self.path.exists())

    def test_invalid_json_is_reported_and_not_replaced(self):
        self.path.write_text("broken-json")
        with self.assertRaisesRegex(RuntimeError, "JSON"):
            self.call(write=True)
        self.assertEqual(self.path.read_text(), "broken-json")

    def test_concurrent_metadata_change_is_not_overwritten(self):
        original = self.apps.file_checksums
        def interrupted(*args, **kwargs):
            result = original(*args, **kwargs)
            self.meta["note"] = "CI 新提交"
            self.write_meta()
            return result
        with patch.object(self.apps, "file_checksums", interrupted):
            with self.assertRaisesRegex(RuntimeError, "变化"):
                self.call(write=True)
        self.assertEqual(json.loads(self.path.read_text())["note"], "CI 新提交")
        self.assertNotIn("apkMd5", json.loads(self.path.read_text()))

    def test_sync_populates_hashes_even_without_proxy_backend(self):
        self.modules["review.rproxy"] = types.SimpleNamespace(backend_name=lambda: None)
        with patch.dict(sys.modules, {"review.rproxy": self.modules["review.rproxy"]}), \
             patch.object(self.apps, "public_download_routes", return_value={}):
            result = self.apps.sync_proxy_routes(reload=False)
        self.assertEqual(json.loads(self.path.read_text()).get("apkMd5"), MD5)
        self.assertEqual(result["integrity"]["demo"]["status"], "verified")
        self.assertEqual(result["errors"], [])

    def test_sync_reports_each_app_error_without_modifying_bad_metadata(self):
        (self.base / "apk/demo-1.0.apk").unlink()
        before = self.path.read_bytes()
        with patch.dict(sys.modules, {"review.rproxy": types.SimpleNamespace(backend_name=lambda: None)}), \
             patch.object(self.apps, "public_download_routes", return_value={}):
            result = self.apps.sync_proxy_routes(reload=False)
        self.assertTrue(any("demo" in e and "校验" in e for e in result["errors"]))
        self.assertEqual(self.path.read_bytes(), before)

    def test_wrong_values_are_repaired_only_on_explicit_sync(self):
        self.meta.update(apkMd5="0" * 32, apkSha256="0" * 64)
        self.write_meta()
        self.assertEqual(self.call()["status"], "mismatch")
        self.assertEqual(self.call(write=True)["status"], "verified")
        data = json.loads(self.path.read_text())
        self.assertEqual((data["apkMd5"], data["apkSha256"]), (MD5, SHA256))

    def test_replace_failure_retains_original_and_cleans_temporary_file(self):
        before = self.path.read_bytes()
        with patch.object(self.apps.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                self.call(write=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.base.glob(".update-integrity-*.tmp")), [])

    def test_metadata_symlink_is_not_followed(self):
        other = pathlib.Path(self.tmp.name) / "outside.json"
        other.write_text(json.dumps(self.meta))
        self.path.unlink()
        self.path.symlink_to(other)
        with self.assertRaisesRegex(RuntimeError, "符号链接"):
            self.call(write=True)
        self.assertNotIn("apkMd5", json.loads(other.read_text()))

    def test_apk_change_after_hashing_stops_write(self):
        original = self.apps.file_checksums
        before = self.path.read_bytes()
        def interrupted(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.base / "apk/demo-1.0.apk").write_bytes(b"another-release")
            return result
        with patch.object(self.apps, "file_checksums", interrupted):
            with self.assertRaisesRegex(RuntimeError, "变化"):
                self.call(write=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_status_concurrent_metadata_change_is_reported(self):
        original = self.apps.file_checksums
        def interrupted(*args, **kwargs):
            result = original(*args, **kwargs)
            self.meta["apkUrl"] = "apk/demo-2.0.apk"
            self.write_meta()
            return result
        with patch.object(self.apps, "file_checksums", interrupted):
            result = self.apps.update_integrity_status("demo")
        self.assertEqual(result["status"], "error")
        self.assertIn("变化", result["error"])

    def test_uppercase_hashes_are_valid_and_do_not_churn(self):
        self.meta.update(apkMd5=MD5.upper(), apkSha256=SHA256.upper())
        self.write_meta()
        before = self.path.read_bytes()
        self.assertEqual(self.call(write=True)["status"], "verified")
        self.assertEqual(self.path.read_bytes(), before)

    def test_notes_and_archiving_preserve_hashes(self):
        self.call(write=True)
        data = json.loads(self.path.read_text())
        data["changelogs"] = [{"versionName": str(i), "note": "v" + str(i)} for i in range(35)]
        self.path.write_text(json.dumps(data))
        self.apps._maintain_update_json("demo")
        self.apps._write_update_json_note("demo", "1.0", "新说明")
        after = json.loads(self.path.read_text())
        self.assertEqual(after["note"], "新说明")
        self.assertEqual(after["apkMd5"], MD5)
        self.assertEqual(after["apkSha256"], SHA256)
        self.assertEqual(len(after["changelogs"]), 30)

    def test_ci_notify_runs_real_hash_sync_and_returns_status(self):
        with patch.dict(sys.modules, {"review.rproxy": types.SimpleNamespace(backend_name=lambda: None)}), \
             patch.object(self.apps, "public_download_routes", return_value={}), \
             patch.object(self.apps, "pending_apps", return_value={"candidates": []}):
            result = self.apps.ci_notify("demo")
        self.assertTrue(result["ok"])
        self.assertEqual(result["integrity"]["demo"]["status"], "verified")
        self.assertEqual(json.loads(self.path.read_text())["apkSha256"], SHA256)

    def test_versions_handler_exposes_actual_integrity_status(self):
        # 执行真实处理函数，只隔离 FastAPI 注册和其他 API 的模块级依赖。
        source = pathlib.Path(self.apps.__file__).with_name("api.py").read_text()
        function = next(n for n in ast.parse(source).body
                        if isinstance(n, ast.FunctionDef) and n.name == "apps_versions")
        function.decorator_list = []
        namespace = {"A": self.apps, "Depends": lambda _: None, "require_auth": None}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "api.py", "exec"), namespace)
        with patch.object(self.apps, "list_changelogs", return_value={}):
            before = self.path.read_bytes()
            missing = namespace["apps_versions"]("demo")
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(missing["integrity"]["status"], "missing")
            self.call(write=True)
            verified = namespace["apps_versions"]("demo")
        self.assertEqual(verified["integrity"]["status"], "verified")
        self.assertEqual(verified["integrity"]["file"], "apk/demo-1.0.apk")
        self.assertEqual(verified["name"], "demo")
        self.assertTrue(verified["versions"])


if __name__ == "__main__":
    unittest.main()
