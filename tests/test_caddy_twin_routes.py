"""裸域名块与 http:// 孪生块的路由注入回归。

真实故障：站点块与其 http:// 孪生块归一化后地址相同，_assign_routes 把同一应用
同时分给两块，各自渲染出一模一样的 @dl_* matcher，caddy validate 报
"matcher is defined more than once: @dl_dateforshift_0.1.0016"，同步整体失败。

Isolated: never starts host services or containers.
"""
import re
import unittest
from unittest.mock import patch

from test_download_routes import _load, _stub_modules

DOMAIN = "update.050709.xyz"
DATA = {"apps": [{"name": "dateforshift", "domain": DOMAIN,
                  "versions": [{"version": "0.1.0016", "rel": "apk/a.apk"}],
                  "latest": {"version": "0.1.0016", "rel": "apk/a.apk"}}]}

MARK = ("    # >>> AUPS APPS (managed, do not remove) <<<\n"
        "    # <<< AUPS APPS >>>\n    file_server")


def _site(host):
    return f"{host} {{\n{MARK}\n}}"


BOTH = ("{\n    auto_https disable_redirects\n}\n\n"
        + _site(DOMAIN) + "\n\n" + _site("http://" + DOMAIN) + "\n")


class TwinRouteTests(unittest.TestCase):
    def setUp(self):
        self.modules = patch.dict(__import__("sys").modules, _stub_modules("caddy"))
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.rp = _load("caddy", "rproxy/caddy")
        self.cf = _load("caddy", "caddyfile")

    def test_route_assigned_to_one_block_only(self):
        blocks = self.rp._managed_sites(BOTH)
        self.assertEqual(len(blocks), 2)
        assign = self.rp._assign_routes(blocks, DATA)
        # 同一逻辑站点只能有一个块拿到路由
        self.assertEqual(sum(1 for v in assign.values() if v), 1)

    def test_duplicate_version_in_data_deduped(self):
        # 真实故障源：应用目录里两个文件解析出同一版本号，list_versions 返回两条
        # 同 version 记录，渲染出重复 matcher。渲染层必须按版本去重。
        dup = {"apps": [{"name": "dateforshift", "domain": DOMAIN,
                         "versions": [{"version": "0.1.0016", "rel": "apk/a.apk"},
                                      {"version": "0.1.0016", "rel": "apk/b.apk"}],
                         "latest": {"version": "0.1.0016", "rel": "apk/a.apk"}}]}
        out = self.rp._render_routes(dup)
        defs = re.findall(r"^\s*(@[\w.\-]+)\s+\S", out, re.MULTILINE)
        self.assertEqual(len(defs), len(set(defs)), defs)

    def test_waf_regex_braces_do_not_break_parsing(self):
        # 真实故障：WAF 正则含字面量括号（\\$\\{、{0,80}），字符级深度计数被
        # 带偏后两个站点块被吞成一个，重建的孪生块尾部多出孤立 }，
        # caddy 报 "subject does not qualify for certificate: '}'"
        waf = ("    @waf_rule_4 {\n"
               "        path_regexp (?i)(;\\s*(ls|cat)\\b|\\$\\{|%00)\n"
               "    }\n"
               "    @waf_rule_8 {\n"
               "        path_regexp (?i)(\\{?\\{.{0,80}?\\}\\}?|\\$\\{\\{)\n"
               "    }\n"
               "    respond @waf_rule_4 403\n")
        text = ("{\n    auto_https disable_redirects\n}\n\n"
                + DOMAIN + " {\n" + waf + "    file_server\n}\n\n"
                + "http://" + DOMAIN + " {\n    file_server\n}\n")
        for mod in (self.rp, self.cf):
            blocks = mod._site_blocks(text)
            self.assertEqual([b["host"] for b in blocks],
                             [DOMAIN, "http://" + DOMAIN], "块边界被正则带偏")
        with patch.object(self.cf, "_port_state",
                          lambda *a, **k: (80, 443, set(), True)):
            fixed = self.cf.ensure_http_listener(
                "{\n    auto_https disable_redirects\n}\n\n"
                + DOMAIN + " {\n" + waf + "    file_server\n}\n")
        self.assertIsNone(re.search(r"\n\}\n\}\n", fixed), "孪生块后出现孤立 }")

    def test_render_yields_unique_matchers(self):
        blocks = self.rp._managed_sites(BOTH)
        assign = self.rp._assign_routes(blocks, DATA)
        twin = {}
        for addr, i in self.rp._logical_sites(blocks).items():
            for j, t in enumerate(blocks):
                if (j != i and self.rp._site_addresses(t["host"]) & {addr}
                        and t["host"].strip().startswith("http://")):
                    twin[j] = i
        parts = []
        for i, t in enumerate(blocks):
            apps = assign[i] or assign.get(twin.get(i, -1), [])
            sn = self.rp._render_routes({"apps": apps})
            if t["host"].strip().startswith("http://"):
                sn = self.cf._rename_matchers(sn)
            parts.append(sn)
        defs = re.findall(r"^\s*(@[\w.\-]+)\s+\S", "\n".join(parts), re.MULTILINE)
        self.assertEqual(len(defs), len(set(defs)), defs)
        # 两个块都要能服务短链，否则 80 端口 404
        joined = "\n".join(parts)
        self.assertIn("@dl_latest_dateforshift", joined)
        self.assertIn("@aups80_dl_latest_dateforshift", joined)


if __name__ == "__main__":
    unittest.main()
