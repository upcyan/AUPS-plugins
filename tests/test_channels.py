"""发布渠道分类回归（release/pr/beta/canary）。

覆盖：渠道识别（文件名 token 与渠道子目录两种方式）、渲染层渠道短链、
无文件的渠道不渲染失效短链。
Isolated: never starts host services or containers.
"""
import re
import unittest
from unittest.mock import patch

from test_download_routes import _load, _stub_modules

CASES = [
    ("dateforshift_1.2.0.apk", "release"),
    ("dateforshift_pr_1.2.1.apk", "pr"),
    ("dateforshift-beta-1.3.0.apk", "beta"),
    ("dateforshift_canary_1.4.0.apk", "canary"),
    ("pr/dateforshift_1.2.2.apk", "pr"),
    ("beta/dateforshift_1.3.1.apk", "beta"),
    ("canary/dateforshift_1.4.1.apk", "canary"),
    ("dateforshift_1.2.0_beta2.apk", "beta"),
    ("prolib_1.0.apk", "release"),
]


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.modules = patch.dict(__import__("sys").modules, _stub_modules("caddy"))
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.au = _load("appupdate", "apps")
        self.rp = _load("caddy", "rproxy/caddy")

    def test_channel_of(self):
        for rel, want in CASES:
            self.assertEqual(self.au.channel_of(rel, "dateforshift"), want, rel)

    def test_render_channel_shortlinks(self):
        data = {"apps": [{
            "name": "dateforshift", "domain": "update.050709.xyz",
            "versions": [{"version": "1.2.0", "rel": "apk/a.apk"}],
            "latest": {"version": "1.2.0", "rel": "apk/a.apk"},
            "latest_by_channel": {
                "release": {"version": "1.2.0", "rel": "apk/a.apk"},
                "pr": {"version": "1.2.1", "rel": "apk/pr/x.apk"},
                "beta": {"version": "1.3.0", "rel": "apk/b.apk"},
                "canary": None,
            }}]}
        sn = self.rp._render_routes(data)
        for path in ("/dateforshift/latest", "/dateforshift/latest-pr",
                     "/dateforshift/latest-beta"):
            self.assertIn(f"path {path}\n", sn, path)
        # canary 无文件 → 不渲染失效短链
        self.assertNotIn("latest-canary", sn)


if __name__ == "__main__":
    unittest.main()
