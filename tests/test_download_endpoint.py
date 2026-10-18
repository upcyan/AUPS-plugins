"""版本页 APK 下载端点的路径校验回归。

download_file_path 是下载端点的安全边界：realPath 限定应用目录、拒绝越界与
不存在文件；与 file_checksums 同规则但不计算哈希（下载是流式转发）。
Isolated: never starts host services or containers.
"""
import os
import tempfile
import types
import unittest
from unittest.mock import patch

from test_download_routes import _load, _stub_modules


class DownloadPathTests(unittest.TestCase):
    def setUp(self):
        self.modules = patch.dict(__import__("sys").modules, _stub_modules("appupdate"))
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.au = _load("appupdate", "apps")
        tmp = tempfile.mkdtemp()
        appdir = os.path.join(tmp, "dateforshift")
        os.makedirs(os.path.join(appdir, "sub"))
        with open(os.path.join(appdir, "app-1.0.apk"), "wb") as f:
            f.write(b"PK" + b"A" * 100)
        with open(os.path.join(appdir, "sub", "b-2.0.apk"), "wb") as f:
            f.write(b"PKsub")
        import json
        cfg = types.ModuleType("config")
        cfg.APPS_FILE = os.path.join(tmp, "apps.json")
        cfg.BASE_DIR = tmp
        cfg.CONF_DIR = tmp
        json.dump({"apps": {"dateforshift": {"dir": appdir}}},
                  open(cfg.APPS_FILE, "w"))
        self.au.config = cfg

    def test_flat_and_subdir_resolve(self):
        self.assertTrue(self.au.download_file_path(
            "dateforshift", "app-1.0.apk").endswith("app-1.0.apk"))
        self.assertTrue(self.au.download_file_path(
            "dateforshift", "sub/b-2.0.apk").endswith("b-2.0.apk"))

    def test_traversal_and_missing_rejected(self):
        for bad in ("../../etc/passwd", "/etc/passwd", ".git/config", "nope.apk"):
            with self.assertRaises(Exception, msg=bad):
                self.au.download_file_path("dateforshift", bad)

    def test_symlink_escape_rejected(self):
        # realPath 约束：指向应用目录外的符号链接必须拒绝
        link = os.path.join(
            self.au.config.BASE_DIR, "dateforshift", "evil.apk")
        os.symlink("/etc/passwd", link)
        with self.assertRaises(Exception):
            self.au.download_file_path("dateforshift", "evil.apk")


if __name__ == "__main__":
    unittest.main()
