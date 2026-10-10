"""下载路由渲染回归测试（caddy / nginx 两个后端）。

覆盖缺陷：latest 与版本短链是无扩展名路径，若由 file_server 直接托管，
响应缺 Content-Type，叠加 X-Content-Type-Options: nosniff 后浏览器禁止嗅探，
APK 被当文本内联渲染而非下载。修复后短链 302 到带扩展名的真实文件，且真实
文件补 Content-Disposition: attachment。

Isolated: never starts host services or containers.
"""
import importlib.util
import pathlib
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]

_DATA = {"apps": [{
    "name": "progresstoday",
    "versions": [
        {"version": "1.1.0", "rel": "apk/progresstoday-1.1.0.apk"},
        {"version": "1.0", "rel": "apk/progresstoday-1.0.apk"},
    ],
    "latest": {"version": "1.1.0", "rel": "apk/progresstoday-1.1.0.apk"},
}]}

# 真实文件直链的匹配规则（与两个后端渲染出的规则语义一致）
_FILE_RE = re.compile(r"^/progresstoday/.*\.(apk|jar|zip|tar\.gz)$")


def _stub_modules(plugin):
    """构造插件相对导入所需的模块桩（config/errors/util/core/env）。

    caddy.py 用 `from .. import env`、`from .... import ports` 这类形式，属性查找
    也须可见，故除了 sys.modules 还要把子模块挂到父包的属性上。
    """
    mods = {}
    for name in ("review", "review.modules", "review.modules." + plugin,
                 "review.modules.%s.rproxy" % plugin, "review.core"):
        mods[name] = types.ModuleType(name)
        mods[name].__path__ = []
    for name in ("config", "errors", "util", "pkg", "ports"):
        mods["review." + name] = types.ModuleType("review." + name)
    mods["review.config"].plugin_dir = lambda a, b: "/tmp"
    mods["review.config"].get_plugin_params = lambda a: {}
    mods["review.errors"].AppError = RuntimeError
    mods["review.util"].has_cmd = lambda a: True
    mods["review.util"].run = lambda *a, **k: None
    mods["review.core"].waf = types.SimpleNamespace(render_config=lambda: {"enabled": False})
    mods["review.core"].contracts = types.SimpleNamespace(
        call=lambda *a: None, read_data=lambda *a: {"apps": []})
    mods["review.modules.%s.env" % plugin] = types.SimpleNamespace(
        caddy_config_file=lambda: "/tmp/Caddyfile",
        access_log_file=lambda: "/tmp/access.log",
        CADDY_LOG_FILE="/tmp/access.log")
    # 让 `from .... import X` / `from .. import env` 的属性查找可见
    for name in ("config", "errors", "util", "pkg", "ports", "core"):
        setattr(mods["review"], name, mods["review." + name])
    setattr(mods["review.modules." + plugin], "env",
            mods["review.modules.%s.env" % plugin])
    return mods


def _load(plugin, name):
    """按点分模块名加载插件模块，使其相对导入层级与真实包一致。"""
    parts = name.split("/")
    spec = importlib.util.spec_from_file_location(
        "review.modules.%s.%s" % (plugin, ".".join(parts)),
        ROOT / "plugins" / plugin / "module" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    if len(parts) > 1:
        sys.modules["review.modules.%s.%s" % (plugin, parts[0])] = sys.modules[
            "review.modules.%s" % plugin]
    spec.loader.exec_module(module)
    return module


class DownloadRouteTests(unittest.TestCase):
    def setUp(self):
        self.patch = patch.dict(sys.modules, _stub_modules("caddy"))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(lambda: [sys.modules.pop(k, None) for k in list(sys.modules)
                                 if k.startswith("review.modules.")])

    # ---------- caddy ----------

    def _caddy(self):
        mod = _load("caddy", "rproxy/caddy")
        mod._download_routes = lambda: _DATA
        return mod

    def test_caddy_shortlinks_redirect_to_real_file(self):
        """latest 与版本短链必须是 302 到带扩展名的真实文件（不再由 file_server 直吐）。"""
        out = self._caddy()._gen_download_routes()
        self.assertIn("@dl_latest_progresstoday path /progresstoday/latest", out)
        self.assertIn("redir @dl_latest_progresstoday "
                      "/progresstoday/apk/progresstoday-1.1.0.apk", out)
        self.assertIn("redir @dl_progresstoday_1.1.0 "
                      "/progresstoday/apk/progresstoday-1.1.0.apk", out)
        self.assertIn("@dl_progresstoday_1.1.0 path /progresstoday/1.1.0 "
                      "/progresstoday/v1.1.0", out)

    def test_caddy_real_files_force_attachment(self):
        """真实文件直链补 Content-Disposition: attachment，且用 path_regexp 以跨子目录。"""
        out = self._caddy()._gen_download_routes()
        self.assertIn('header @dl_file_progresstoday Content-Disposition "attachment"', out)
        # path 的 * 不跨 /，故必须用 path_regexp，否则 /app/apk/x.apk 匹配不到
        m = re.search(r"@dl_file_progresstoday (path_regexp \S+ )?(\S+)$", out, re.M)
        self.assertIsNotNone(m)
        self.assertIn("path_regexp", m.group(0))
        self.assertNotIn("path /progresstoday/*.apk", out)

    def test_caddy_regex_matches_nested_paths_only(self):
        """渲染出的正则须覆盖子目录真实文件，且不误伤短链/update.json。"""
        out = self._caddy()._gen_download_routes()
        pattern = re.search(r"@dl_file_progresstoday path_regexp \S+ (\S+)$", out, re.M).group(1)
        rx = re.compile(pattern)
        for p in ("/progresstoday/apk/progresstoday-1.1.0.apk",
                  "/progresstoday/a.jar", "/progresstoday/a.zip",
                  "/progresstoday/a.tar.gz"):
            self.assertTrue(rx.match(p), p)
        for p in ("/progresstoday/latest", "/progresstoday/1.1.0",
                  "/progresstoday/update.json", "/other/x.apk"):
            self.assertIsNone(rx.match(p), p)

    def test_caddy_no_content_type_override(self):
        """不覆盖 Content-Type：jar/zip 应保留 file_server 按扩展名的推断结果。"""
        out = self._caddy()._gen_download_routes()
        self.assertNotIn("Content-Type", out)

    def test_caddy_empty_data_keeps_valid_markers(self):
        """无 appupdate 数据时仍生成成对标记区，不产生悬空规则。"""
        mod = self._caddy()
        mod._download_routes = lambda: {"apps": []}
        out = mod._gen_download_routes()
        self.assertEqual(out, mod._APPS_MARK_BEGIN + "\n" + mod._APPS_MARK_END)

    # ---------- nginx ----------

    def test_nginx_aligned_behaviour(self):
        """nginx 后端与 caddy 同形：短链 302 + 真实文件 attachment，覆盖子目录。"""
        with patch.dict(sys.modules, _stub_modules("nginx")):
            mod = _load("nginx", "api")
            mod._routes_data = lambda: _DATA
            out = mod._gen_routes_conf()
        self.assertIn("location = /progresstoday/latest "
                      "{ return 302 /progresstoday/apk/progresstoday-1.1.0.apk; }", out)
        self.assertIn('add_header Content-Disposition "attachment";', out)
        pattern = re.search(r"location ~ (\S+) \{", out).group(1)
        rx = re.compile(pattern)
        self.assertTrue(rx.match("/progresstoday/apk/progresstoday-1.1.0.apk"))
        self.assertIsNone(rx.match("/progresstoday/latest"))
        self.assertIsNone(rx.match("/progresstoday/update.json"))

    # ---------- 站点块必须自带托管标记区（apply 的注入前提）----------

    def test_app_site_block_contains_managed_marker(self):
        """应用站点块必须自带 AUPS APPS 标记区。

        回归：标记缺失时 update_app_sites 正常返回、但随后的 apply() 报
        「Caddyfile 中未找到 AUPS 托管标记区」，短链从未注入——线上表现为
        /latest 仍 200 直吐文件、不触发下载。
        """
        with patch.dict(sys.modules, _stub_modules("caddy")):
            cf = _load("caddy", "caddyfile")
            rp = _load("caddy", "rproxy/caddy")
        blocks, _skipped = cf._gen_app_site_blocks(
            [{"name": "progresstoday", "domain": "update.050709.xyz",
              "port": 443, "workdir": "/srv/progresstoday"}])
        self.assertIn(rp._APPS_MARK_BEGIN, blocks)
        self.assertIn(rp._APPS_MARK_END, blocks)
        # 标记区须在站点块内部（root/file_server 之前），而非块外
        body = blocks.split("{", 1)[1].rsplit("}", 1)[0]
        self.assertIn(rp._APPS_MARK_BEGIN, body)
        self.assertIn(rp._APPS_MARK_END, body)
        self.assertLess(body.index(rp._APPS_MARK_BEGIN), body.index("root *"))

    def test_sync_then_apply_injects_routes(self):
        """端到端（文本级）：站点块生成后 apply 必须能成功注入短链与 attachment。

        用真实临时 Caddyfile 走完 update_app_sites → apply 两步，避免 mock 掩盖
        「标记区找不到」这类只在真实写盘后才暴露的失败。
        """
        with patch.dict(sys.modules, _stub_modules("caddy")):
            cf = _load("caddy", "caddyfile")
            rp = _load("caddy", "rproxy/caddy")
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "Caddyfile"
                path.write_text("{\n\tadmin off\n}\n", encoding="utf-8")
                env = types.SimpleNamespace(caddy_config_file=lambda: str(path),
                                            deploy_method=lambda: "host",
                                            caddy_binary=lambda: None)
                with patch.object(cf, "env", env), patch.object(rp, "env", env):
                    cf.update_app_sites([{"name": "progresstoday",
                                          "domain": "update.050709.xyz",
                                          "port": 443, "workdir": "/srv/progresstoday"}],
                                        reload_=False)
                    rp._download_routes = lambda: _DATA
                    result = rp.apply(reload=False)
                body = path.read_text(encoding="utf-8")
        self.assertTrue(result["changed"])
        self.assertIn("@dl_latest_progresstoday path /progresstoday/latest", body)
        self.assertIn("redir @dl_latest_progresstoday "
                      "/progresstoday/apk/progresstoday-1.1.0.apk", body)
        self.assertIn("Content-Disposition", body)
        # 短链规则必须落在应用站点块内（root/file_server 之前），否则不会生效
        self.assertLess(body.index("@dl_latest_progresstoday"), body.index("root *"))

    # ---------- 手写站点块自动接管 ----------

    def _load_pair(self):
        cf = _load("caddy", "caddyfile")
        rp = _load("caddy", "rproxy/caddy")
        return cf, rp

    def _env(self, path):
        return types.SimpleNamespace(caddy_config_file=lambda: str(path),
                                     deploy_method=lambda: "host",
                                     caddy_binary=lambda: None)

    def test_adopts_handwritten_site_block(self):
        """手写站点块（无标记）应被就地接管，且用户原有指令逐行保留。

        回归：此前 update_app_sites 把已占用域名的站点判为「保留并跳过」，该块
        永远拿不到标记区，apply() 随即报错，短链注入不进去。
        """
        handwritten = ("{\n\tadmin off\n}\n\n"
                       "update.050709.xyz {\n"
                       "\theader X-Frame-Options DENY\n"
                       "\troot * /srv/progresstoday\n"
                       "\tfile_server\n"
                       "}\n")
        with patch.dict(sys.modules, _stub_modules("caddy")):
            cf, rp = self._load_pair()
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "Caddyfile"
                path.write_text(handwritten, encoding="utf-8")
                env = self._env(path)
                with patch.object(cf, "env", env), patch.object(rp, "env", env):
                    r1 = cf.update_app_sites(
                        [{"name": "progresstoday", "domain": "update.050709.xyz",
                          "port": 443, "workdir": "/srv/progresstoday"}], reload_=False)
                    rp._download_routes = lambda: _DATA
                    r2 = rp.apply(reload=False)
                body = path.read_text(encoding="utf-8")
        # 被接管（而非跳过），并记录了新增项
        self.assertEqual([a["domain"] for a in r1["adopted"]], ["update.050709.xyz"])
        self.assertNotIn("update.050709.xyz", r1["skipped_existing"])
        # 用户配置原样保留，未被覆盖或重复
        self.assertIn("header X-Frame-Options DENY", body)
        self.assertEqual(body.count("header X-Frame-Options DENY"), 1)
        self.assertEqual(body.count("file_server"), 1)
        # 托管标记与短链都已注入
        self.assertTrue(r2["changed"])
        self.assertIn(rp._APPS_MARK_BEGIN, body)
        self.assertIn("@dl_latest_progresstoday path /progresstoday/latest", body)

    def test_sync_is_idempotent(self):
        """重复同步必须收敛：第二轮起不再认定「有变化」，以免每次写盘 + reload。"""
        with patch.dict(sys.modules, _stub_modules("caddy")):
            cf, rp = self._load_pair()
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "Caddyfile"
                path.write_text("{\n\tadmin off\n}\n", encoding="utf-8")
                env = self._env(path)
                apps = [{"name": "progresstoday", "domain": "update.050709.xyz",
                         "port": 443, "workdir": "/srv/progresstoday"}]
                with patch.object(cf, "env", env), patch.object(rp, "env", env):
                    rp._download_routes = lambda: _DATA
                    cf.update_app_sites(apps, reload_=False)
                    rp.apply(reload=False)
                    first = path.read_text(encoding="utf-8")
                    r1 = cf.update_app_sites(apps, reload_=False)
                    r2 = rp.apply(reload=False)
                    second = path.read_text(encoding="utf-8")
        self.assertTrue(r1["unchanged"], "第二轮 update_app_sites 不应再写盘")
        self.assertFalse(r2["changed"], "第二轮 apply 不应再写盘与 reload")
        self.assertEqual(first, second)

    def test_routes_are_scoped_per_domain(self):
        """多应用多域名时，每个站点块只应收到自己域名下应用的路由。"""
        apps = [{"name": "progresstoday", "domain": "update.050709.xyz",
                 "port": 443, "workdir": "/srv/progresstoday"},
                {"name": "otherapp", "domain": "dl.example.com",
                 "port": 443, "workdir": "/srv/otherapp"}]
        data = {"apps": [
            {"name": "progresstoday", "domain": "update.050709.xyz",
             "versions": [{"version": "1.1.0", "rel": "apk/p.apk"}],
             "latest": {"version": "1.1.0", "rel": "apk/p.apk"}},
            {"name": "otherapp", "domain": "dl.example.com",
             "versions": [{"version": "2.0", "rel": "apk/o.apk"}],
             "latest": {"version": "2.0", "rel": "apk/o.apk"}}]}
        with patch.dict(sys.modules, _stub_modules("caddy")):
            cf, rp = self._load_pair()
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "Caddyfile"
                path.write_text("{\n\tadmin off\n}\n", encoding="utf-8")
                env = self._env(path)
                with patch.object(cf, "env", env), patch.object(rp, "env", env):
                    rp._download_routes = lambda: data
                    cf.update_app_sites(apps, reload_=False)
                    result = rp.apply(reload=False)
                body = path.read_text(encoding="utf-8")
        self.assertEqual(result["sites"], 2)
        # 按站点块切分后校验归属，避免把 /otherapp/latest 写进无关站点
        for blk in re.split(r"\n(?=\S+\s*\{)", body):
            host = blk.split("{")[0].strip()
            if host == "update.050709.xyz":
                self.assertIn("/progresstoday/latest", blk)
                self.assertNotIn("/otherapp/", blk)
            elif host == "dl.example.com":
                self.assertIn("/otherapp/latest", blk)
                self.assertNotIn("/progresstoday/", blk)

    def test_unmatched_domain_routes_fall_back(self):
        """配了域名但无对应站点块的应用，短链必须兜底保留（否则 App 下载 404）。

        回归：按域名过滤时若只认「有站点块」的应用，未部署站点、或站点块同步
        失败（sync 的站点步报错后 apply 仍会执行）的应用路由会整段丢失。
        """
        apps = [{"name": "progresstoday", "domain": "update.050709.xyz",
                 "port": 443, "workdir": "/srv/progresstoday"}]
        data = {"apps": [
            {"name": "progresstoday", "domain": "update.050709.xyz",
             "versions": [{"version": "1.1.0", "rel": "apk/p.apk"}],
             "latest": {"version": "1.1.0", "rel": "apk/p.apk"}},
            {"name": "ghost", "domain": "nowhere.example.com",
             "versions": [{"version": "3.0", "rel": "apk/g.apk"}],
             "latest": {"version": "3.0", "rel": "apk/g.apk"}}]}
        with patch.dict(sys.modules, _stub_modules("caddy")):
            cf, rp = self._load_pair()
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "Caddyfile"
                path.write_text("{\n\tadmin off\n}\n", encoding="utf-8")
                env = self._env(path)
                with patch.object(cf, "env", env), patch.object(rp, "env", env):
                    rp._download_routes = lambda: data
                    cf.update_app_sites(apps, reload_=False)
                    rp.apply(reload=False)
                body = path.read_text(encoding="utf-8")
        self.assertIn("/progresstoday/latest", body)
        self.assertIn("/ghost/latest", body, "无站点块的域名也须保留短链")

    def test_no_domain_apps_still_routed(self):
        """未绑定域名的应用，其短链仍须注入托管块（兼容旧配置，避免路由丢失）。"""
        apps = [{"name": "progresstoday", "domain": "update.050709.xyz",
                 "port": 443, "workdir": "/srv/progresstoday"},
                {"name": "legacy", "domain": "", "port": 0, "workdir": "/srv/legacy"}]
        data = {"apps": [
            {"name": "progresstoday", "domain": "update.050709.xyz",
             "versions": [{"version": "1.1.0", "rel": "apk/p.apk"}],
             "latest": {"version": "1.1.0", "rel": "apk/p.apk"}},
            {"name": "legacy", "domain": "",
             "versions": [{"version": "0.9", "rel": "apk/l.apk"}],
             "latest": {"version": "0.9", "rel": "apk/l.apk"}}]}
        with patch.dict(sys.modules, _stub_modules("caddy")):
            cf, rp = self._load_pair()
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "Caddyfile"
                path.write_text("{\n\tadmin off\n}\n", encoding="utf-8")
                env = self._env(path)
                with patch.object(cf, "env", env), patch.object(rp, "env", env):
                    rp._download_routes = lambda: data
                    cf.update_app_sites(apps, reload_=False)
                    rp.apply(reload=False)
                body = path.read_text(encoding="utf-8")
        self.assertIn("/progresstoday/latest", body)
        self.assertIn("/legacy/latest", body)

    def test_assign_routes_rules(self):
        """_assign_routes 的分配规则：域名匹配只进该块，未匹配兜底进首块，无域名进所有块。"""
        blocks = [{"host": "a.example.com"}, {"host": "b.example.com"}]
        data = {"apps": [
            {"name": "x", "domain": "a.example.com"},
            {"name": "y", "domain": "b.example.com"},
            {"name": "z", "domain": ""},
            {"name": "w", "domain": "gone.example.com"}]}
        with patch.dict(sys.modules, _stub_modules("caddy")):
            _cf, rp = self._load_pair()
            assign = rp._assign_routes(blocks, data)
        self.assertEqual([a["name"] for a in assign[0]], ["x", "z", "w"])
        self.assertEqual([a["name"] for a in assign[1]], ["y", "z"])

    def test_clear_routes_covers_all_sites(self):
        """clear_routes 须清空每个托管站点块的短链（迁移切换后不留陈旧重定向）。"""
        apps = [{"name": "progresstoday", "domain": "update.050709.xyz",
                 "port": 443, "workdir": "/srv/progresstoday"},
                {"name": "otherapp", "domain": "dl.example.com",
                 "port": 443, "workdir": "/srv/otherapp"}]
        data = {"apps": [
            {"name": "p", "domain": "update.050709.xyz",
             "versions": [{"version": "1", "rel": "a.apk"}],
             "latest": {"version": "1", "rel": "a.apk"}},
            {"name": "o", "domain": "dl.example.com",
             "versions": [{"version": "1", "rel": "b.apk"}],
             "latest": {"version": "1", "rel": "b.apk"}}]}
        data["apps"][0]["name"], data["apps"][1]["name"] = "progresstoday", "otherapp"
        with patch.dict(sys.modules, _stub_modules("caddy")):
            cf, rp = self._load_pair()
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "Caddyfile"
                path.write_text("{\n\tadmin off\n}\n", encoding="utf-8")
                env = self._env(path)
                with patch.object(cf, "env", env), patch.object(rp, "env", env):
                    rp._download_routes = lambda: data
                    cf.update_app_sites(apps, reload_=False)
                    rp.apply(reload=False)
                    rp.clear_routes(reload=False)
                body = path.read_text(encoding="utf-8")
        self.assertEqual(body.count("/latest"), 0)
        # 站点块与文件服务配置保留，仅短链被清空
        self.assertIn("file_server", body)
        self.assertIn("root * /srv/progresstoday", body)
        self.assertIn("root * /srv/otherapp", body)


if __name__ == "__main__":
    unittest.main()
