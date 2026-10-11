"""旧托管块升级、独立 apply 自动补标记与失败回滚回归。"""
import pathlib
import tempfile
import types
import unittest
from unittest.mock import patch

from test_download_routes import _load, _stub_modules

DOMAIN = "update.050709.xyz"
APPS = [{"name": name, "domain": DOMAIN, "workdir": "/var/www/html/" + name}
        for name in ("dateforshift", "progresstoday")]
DATA = {"apps": [{"name": app["name"], "domain": DOMAIN,
                  "versions": [{"version": "1.0", "rel": "apk/app-1.0.apk"}],
                  "latest": {"version": "1.0", "rel": "apk/app-1.0.apk"}}
                 for app in APPS]}
SITE = (DOMAIN + " {\n    header X-Frame-Options DENY\n"
        "    root * /var/www/html\n    file_server\n}\n")


class CaddyMarkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name) / "Caddyfile"
        self.path.write_text(SITE)
        self.modules = patch.dict(__import__('sys').modules, _stub_modules("caddy"))
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.cf = _load("caddy", "caddyfile")
        self.rp = _load("caddy", "rproxy/caddy")
        self.env = types.SimpleNamespace(caddy_config_file=lambda: str(self.path),
                                         deploy_method=lambda: "host", caddy_binary=lambda: None,
                                         instance=lambda *args: None)
        for module in (self.cf, self.rp):
            p = patch.object(module, "env", self.env)
            p.start()
            self.addCleanup(p.stop)
        self.rp._download_routes = lambda: DATA

    def test_upgrade_old_managed_block_repairs_missing_marker(self):
        self.path.write_text(self.cf._APPS_SITE_BEGIN + "\n" + SITE +
                             self.cf._APPS_SITE_END + "\n")
        self.cf.update_app_sites(APPS, reload_=False)
        self.assertIn(self.rp._APPS_MARK_BEGIN, self.path.read_text(),
                      "复用旧托管块时必须补标记，不能原样复用缺标记的 body")
        self.rp.apply(reload=False)
        self.check_shared_domain()
        self.assertTrue(self.cf.update_app_sites(APPS, reload_=False)["unchanged"])
        self.assertFalse(self.rp.apply(reload=False)["changed"])

    def check_shared_domain(self):
        result = self.path.read_text()
        self.assertEqual(result.count(DOMAIN + " {"), 1)
        self.assertIn("root * /var/www/html\n", result)
        self.assertIn("header X-Frame-Options DENY", result)
        for app in APPS:
            self.assertIn("/" + app["name"] + "/latest", result)
        self.assertIn('Content-Disposition "attachment"', result)

    def test_apply_itself_repairs_registered_domain_without_previous_site_sync(self):
        try:
            self.rp.apply(reload=False)
        except RuntimeError as e:
            self.fail("apply 应自行补标记，不能要求用户手工添加：" + str(e))
        self.check_shared_domain()
        self.assertFalse(self.rp.apply(reload=False)["changed"])

    def test_existing_other_managed_site_does_not_hide_unmarked_app_site(self):
        self.path.write_text("unrelated.example.com {\n    " + self.rp._APPS_MARK_BEGIN +
                             "\n    " + self.rp._APPS_MARK_END +
                             "\n    respond \"unrelated\"\n}\n" + SITE)
        self.rp.apply(reload=False)
        blocks = self.rp._site_blocks(self.path.read_text())
        target = next(b for b in blocks if b["host"] == DOMAIN)
        self.assertIn("/progresstoday/latest", target["body"],
                      "即使其他块已有标记，也必须修复应用自己的块")
        other = next(b for b in blocks if b["host"] == "unrelated.example.com")
        self.assertNotIn("/progresstoday/latest", other["body"])

    def test_unrelated_unmarked_site_is_not_adopted_as_fallback(self):
        self.path.write_text("unrelated.example.com {\n    root * /private\n    file_server\n}\n")
        before = self.path.read_bytes()
        with self.assertRaises(RuntimeError):
            self.rp.apply(reload=False)
        self.assertEqual(self.path.read_bytes(), before)

    def test_lone_begin_marker_does_not_swallow_root_or_fileserver(self):
        self.path.write_text(SITE.replace("    root *", "    " + self.rp._APPS_MARK_BEGIN +
                                         "\n    root *"))
        self.rp.apply(reload=False)
        self.check_shared_domain()

    def test_failed_validation_does_not_write_repaired_config(self):
        before = self.path.read_bytes()
        # 现有标记用于避免基线先因找不到标记失败；此测试只保护保存前校验。
        self.path.write_text(SITE.replace("    root *", "    " + self.rp._APPS_MARK_BEGIN +
                                         "\n    " + self.rp._APPS_MARK_END + "\n    root *"))
        before = self.path.read_bytes()
        with patch.object(self.cf, "_validate", return_value="invalid Caddyfile"):
            with self.assertRaisesRegex(RuntimeError, "校验失败"):
                self.rp.apply(reload=False)
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_reload_restores_original_config_and_reports_error(self):
        self.path.write_text(SITE.replace("    root *", "    " + self.rp._APPS_MARK_BEGIN +
                                         "\n    " + self.rp._APPS_MARK_END + "\n    root *"))
        before = self.path.read_bytes()
        self.env.instance = lambda *args: (_ for _ in ()).throw(RuntimeError("reload failed"))
        with self.assertRaisesRegex(RuntimeError, "reload 失败"):
            self.rp.apply(reload=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_lone_end_marker_is_completed_without_duplicate_sections(self):
        self.path.write_text(SITE.replace("    root *", "    " + self.rp._APPS_MARK_END +
                                         "\n    root *"))
        self.rp.apply(reload=False)
        self.check_shared_domain()
        self.assertEqual(self.path.read_text().count(self.rp._APPS_MARK_BEGIN), 1)
        self.assertEqual(self.path.read_text().count(self.rp._APPS_MARK_END), 1)

    def test_legacy_marker_pair_remains_compatible(self):
        self.path.write_text(SITE.replace("    root *", "    " + self.rp._OLD_APPS_BEGIN +
                                         "\n    " + self.rp._OLD_APPS_END + "\n    root *"))
        self.rp.apply(reload=False)
        self.check_shared_domain()
        self.assertEqual(self.path.read_text().count(self.rp._APPS_MARK_BEGIN), 1)
        self.assertNotIn(self.rp._OLD_APPS_BEGIN, self.path.read_text())


if __name__ == "__main__":
    unittest.main()
