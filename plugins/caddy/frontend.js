/* AUPS 插件：caddy — 反代配置（WAF 模板已移至「安全管理 → WAF 模板」）
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['caddy'] = (function () {
  const P = 'AUPS_PLUGINS.caddy.';
  let section = 'rproxy';

  function navHtml() {
    return `<div class="secnav">
      <button class="${section === 'rproxy' ? 'on' : ''}" onclick="${P}go('rproxy')">反代配置</button>
    </div>`;
  }

  function go(s) {
    section = s || 'rproxy';
    if (section === 'rproxy') rproxyTab();
  }

  /* ---------- 反代配置 ---------- */
  async function rproxyTab() {
    const [st, pt] = await Promise.all([
      api('GET', '/api/caddyconf/status'),
      api('GET', '/api/ports')
    ]);
    const caddy = pt.caddy || {};
    const listening = (pt.listening || []).map(x => `${x.local}  (${x.process})`).join('\n');
    view.innerHTML = navHtml() + `
    <div class="card"><h2>反代后端 · ${esc(st.backend)}</h2>
      <div class="row">
        <span>配置: <span class="mut">${esc(st.caddyfile || '-')}</span></span>
        ${st.name === 'caddy' ? `<span class="mut">Caddy ${esc(st.version || '未知')} · reload: ${esc(st.reload_method || '-')}</span>` : ''}
      </div>
      <div class="row" style="margin-top:10px">
        <button class="ghost" onclick="${P}caddyPreview()">预览片段</button>
        <button onclick="${P}caddyApply()">应用并 reload</button>
      </div>
      <div class="mut" style="margin-top:10px">下载路由 + WAF 规则由面板写入 Caddyfile（AUPS APPS / AUPS WAF 标记区）。WAF 规则模板在「安全管理 → WAF 模板」维护，变更后自动重载本反代。</div>
    </div>
    <div class="card"><h2>Caddy HTTPS 端口</h2>
      <div class="row">
        <span>当前: <b>${esc(caddy.https_port || '未配置')}</b></span>
        <input id="portVal" type="text" placeholder="新端口，如 2096">
        <button onclick="${P}setCaddyPort()">修改并 reload</button>
      </div>
      <div class="mut" style="margin-top:6px">面板自身端口在「面板设置 → 面板端口」查看。</div></div>
    <div class="card"><h2>监听端口</h2><pre>${listening || '无'}</pre></div>
    <div id="ccPreviewBox"></div>`;
  }
  async function setCaddyPort() {
    const p = parseInt(document.getElementById('portVal').value);
    if (isNaN(p)) { alert('请输入端口'); return; }
    await api('POST', '/api/ports/caddy', { port: p });
    await rproxyTab();
  }
  async function caddyPreview() {
    const box = document.getElementById('ccPreviewBox');
    const d = await api('GET', '/api/caddyconf/preview');
    box.innerHTML = `<div class="card"><h2>预览（尚未写入）</h2>
      <h2 class="mut">下载路由</h2><pre>${esc(d.apps)}</pre>
      <h2 class="mut">WAF（来自核心模板）</h2><pre>${esc(d.waf)}</pre></div>`;
  }
  async function caddyApply() { await api('POST', '/api/caddyconf/apply', { reload: true }); alert('已写入 Caddyfile 并 reload'); await rproxyTab(); }

  return {
    title: 'Caddy 环境',
    sections: [{ id: 'rproxy', title: '反代配置' }],
    go: go,
    open: function (s) { go(s || 'rproxy'); },
    rproxyTab: rproxyTab,
    setCaddyPort: setCaddyPort, caddyPreview: caddyPreview, caddyApply: caddyApply,
  };
})();
