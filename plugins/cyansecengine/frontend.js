/* AUPS 插件：cyansecengine —— 青·擎统一安全总览 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS.cyansecengine = (function () {
  const P = 'AUPS_PLUGINS.cyansecengine.';
  let data = null;

  const safe = v => v == null ? '-' : String(v);
  const ok = v => v ? '<span class="ok">正常</span>' : '<span class="bad">异常</span>';
  const provider = (v, fallback) => safe((v && v.provider) || fallback || '核心/未安装');

  async function load() {
    const root = view('cyansecengine');
    if (!root) return;
    root.innerHTML = '<div class="card"><h2>青·擎</h2><div class="mut">正在读取安全引擎状态…</div></div>';
    try {
      data = await api('GET', '/api/cyansecengine/status');
      render(root);
    } catch (e) {
      root.innerHTML = `<div class="card"><h2>青·擎</h2><div class="bad">加载失败：${esc((e && e.message) || e)}</div></div>`;
    }
  }

  function render(root) {
    const fw = data.firewall || {};
    const fs = fw.status || {};
    const vs = (data.vulnerability || {}).status || {};
    const hs = data.hostsec || {};
    const rt = data.realtime || {};
    const w = data.waf || {};
    root.innerHTML = `<div class="card">
      <div class="row" style="justify-content:space-between;align-items:center">
        <div><h2 style="margin:0">青·擎安全总览</h2><div class="mut">统一编排防火墙、WAF、漏洞检测、主机安全与实时防护</div></div>
        <button class="ghost" onclick="${P}load()">刷新</button>
      </div>
      <div class="grid" style="margin-top:14px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">
        <div class="card"><h3>防火墙</h3><div>引擎：${provider(fw, 'secgroup')}</div><div>状态：${ok(fs.active !== false && fs.installed !== false)}</div><div class="mut">规则 ${safe((fs.rules || []).length)}</div></div>
        <div class="card"><h3>WAF</h3><div>状态：${ok(!!w.enabled)}</div><div class="mut">规则 ${safe((w.rules || []).length)}，黑名单 ${safe((w.blacklist_ips || []).length)}</div></div>
        <div class="card"><h3>漏洞检测</h3><div>引擎：${provider(data.vulnerability, '未安装')}</div><div>状态：${ok(vs.installed !== false)}</div><div class="mut">Linux：${safe(vs.linux)}</div></div>
        <div class="card"><h3>主机安全</h3><div>报告目录：${safe(hs.reports_dir)}</div><div class="mut">引擎按能力从插件中心提供</div></div>
        <div class="card"><h3>实时防护</h3><div>状态：${rt.enabled ? '<span class="ok">已启用</span>' : '<span class="mut">未启用</span>'}</div><div class="mut">监控目录 ${safe((rt.paths || []).length)}</div></div>
      </div>
      <div class="row" style="margin-top:14px;gap:8px;flex-wrap:wrap">
        <button onclick="show('security')">打开安全管理</button>
        <button class="ghost" onclick="${P}check(this)">运行漏洞检查</button>
      </div>
      <div id="cyanCheck" class="mut" style="margin-top:10px"></div>
    </div>`;
  }

  async function check(btn) {
    const done = beginButtonTask(btn);
    const box = document.getElementById('cyanCheck');
    try {
      const r = await api('POST', '/api/cyansecengine/check');
      box.className = r.ok ? 'ok' : 'bad';
      box.textContent = r.vulnerability ? r.vulnerability.summary : '暂无可用漏洞检测引擎';
    } catch (e) { box.className = 'bad'; box.textContent = '检查失败：' + ((e && e.message) || e); }
    finally { done(); }
  }

  return {title: '青·擎', sections: [{id: 'overview', title: '安全总览'}], go: load, open: load, overview: load, load, check};
})();
