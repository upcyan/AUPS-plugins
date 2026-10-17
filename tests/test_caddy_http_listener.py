"""80 端口监听回归测试（Cloudflare 521 事故）。

缺陷：全局块写入 auto_https disable_redirects 后，裸域名站点块不再自动绑定 80；
若同时没有显式 http:// 站点块，Caddy 只监听 443。Cloudflare 回源走 80，重启后
全站 521。该状态会落盘，重启即复现，必须由配置写入与实例启动两条路径兜住。

Isolated: never starts host services or containers.
"""
import pathlib
import types
import unittest
from unittest.mock import patch

from test_download_routes import _load, _stub_modules

DOMAIN = "update.050709.xyz"

# 事故现场：只有裸域名站点块 + 已关闭 auto_https
BROKEN = (
    "{\n    auto_https disable_redirects\n}\n\n"
    f"{DOMAIN} {{\n    root * /var/www/html/{DOMAIN}\n    file_server\n}}\n"
)


def _port_state_patch(*args, **kwargs):
    """端口探测固定返回：80/443 均空闲。"""
    return 80, 443, set(), True


class HttpListenerTests(unittest.TestCase):
    def setUp(self):
        self.modules = patch.dict(__import__("sys").modules, _stub_modules("caddy"))
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.cf = _load("caddy", "caddyfile")

    def test_broken_config_is_detected(self):
        self.assertTrue(self.cf._needs_http_listener(BROKEN))

    def test_adds_http_twin_preserving_body(self):
        with patch.object(self.cf, "_port_state", _port_state_patch):
            fixed = self.cf.ensure_http_listener(BROKEN)
        self.assertIn(f"http://{DOMAIN}", fixed)
        # 孪生块必须保留原站点内容，否则 80 端口返回 404 而非正常页面
        self.assertIn(f"root * /var/www/html/{DOMAIN}", fixed)
        self.assertIn("file_server", fixed)
        # 缩进不得叠加：原 body 已带缩进，再加一层会让嵌套块错位
        self.assertIn("\n    file_server\n", fixed)
        self.assertNotIn("        file_server", fixed)
        self.assertTrue(self.cf._has_http_listener(fixed))

    def test_idempotent(self):
        with patch.object(self.cf, "_port_state", _port_state_patch):
            once = self.cf.ensure_http_listener(BROKEN)
            twice = self.cf.ensure_http_listener(once)
        self.assertEqual(once, twice)

    def test_leaves_config_alone_when_auto_https_active(self):
        # auto_https 未被关闭时 Caddy 会自动监听 80，不应重复建块
        content = f"{DOMAIN} {{\n    file_server\n}}\n"
        with patch.object(self.cf, "_port_state", _port_state_patch):
            self.assertEqual(self.cf.ensure_http_listener(content), content)

    def test_leaves_config_alone_when_http_port_taken(self):
        # 80 被占用时补 http 块会让 reload 必然失败，应保持原样
        content = BROKEN
        with patch.object(self.cf, "_port_state",
                          lambda *a, **k: (80, 443, {80}, True)):
            self.assertEqual(self.cf.ensure_http_listener(content), content)

    def test_existing_http_site_not_duplicated(self):
        content = BROKEN + f"\nhttp://{DOMAIN} {{\n    file_server\n}}\n"
        with patch.object(self.cf, "_port_state", _port_state_patch):
            self.assertEqual(self.cf.ensure_http_listener(content), content)

    def test_nested_block_indentation_preserved(self):
        # 嵌套块（reverse_proxy { ... }）复制到孪生块后缩进必须与原块一致
        content = (
            "{\n    auto_https disable_redirects\n}\n\n"
            f"{DOMAIN} {{\n    reverse_proxy localhost:8000 {{\n"
            "        lb_policy round_robin\n    }\n}\n"
        )
        with patch.object(self.cf, "_port_state", _port_state_patch):
            fixed = self.cf.ensure_http_listener(content)
        self.assertIn("http://" + DOMAIN + " {\n    reverse_proxy localhost:8000 {\n"
                      "        lb_policy round_robin\n    }\n}", fixed)

    def test_custom_http_port_does_not_count_as_80(self):
        content = BROKEN + f"\nhttp://{DOMAIN}:8080 {{\n    file_server\n}}\n"
        with patch.object(self.cf, "_port_state", _port_state_patch):
            fixed = self.cf.ensure_http_listener(content)
        self.assertIn(f"http://{DOMAIN} {{", fixed)


if __name__ == "__main__":
    unittest.main()
