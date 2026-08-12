/* AUPS 插件：caddy —— 反代配置 / WAF 防护
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
      <button class="${section === 'waf' ? 'on' : ''}" onclick="${P}go('waf')">WAF 防护</button>
    </div>`;
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
      <div class="mut" style="margin-top:10px">下载路由 + WAF 规则由 aups 写入 Caddyfile（AUPS APPS / AUPS WAF 标记区）。WAF 规则在本插件「WAF 防护」页维护。</div>
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
      <h2 class="mut">WAF</h2><pre>${esc(d.waf)}</pre></div>`;
  }
  async function caddyApply() { await api('POST', '/api/caddyconf/apply', { reload: true }); alert('已写入 Caddyfile 并 reload'); await rproxyTab(); }

  /* ---------- WAF 防护 ---------- */
  async function wafTab() {
    const wf = await api('GET', '/api/caddyconf/waf');
    const rl = wf.rate_limit;
    const rules = wf.rules.map(r => `<tr>
      <td>${esc(r.name || '-')}</td><td>${esc(r.kind)}${r.field ? '<span class="mut"> [' + esc(r.field) + ']</span>' : ''}</td>
      <td>${esc(r.pattern)}</td><td>${r.source || 'local'}</td>
      <td>${r.enabled ? '<span class="ok">启用</span>' : '<span class="bad">停用</span>'}</td>
      <td><div class="row">
        <button class="ghost" onclick="${P}wafToggleRule('${r.id}',${!r.enabled})">${r.enabled ? '停用' : '启用'}</button>
        <button class="danger" onclick="${P}wafDelRule('${r.id}')">删除</button>
      </div></td></tr>`).join('') || '<tr><td colspan="6" class="mut">暂无本地规则</td></tr>';
    const sub = wf.subscriptions.map(s => `<div class="row" style="margin:6px 0">
      <span>${esc(s.name)}</span><span class="mut">${esc(s.url)}</span>
      <span class="mut">${s.rule_count} 条 · ${s.interval_sec}s</span>
      <button class="ghost" onclick="${P}subSync('${esc(s.url)}')">同步</button>
      <button class="danger" onclick="${P}subRemove('${esc(s.url)}')">移除</button>
    </div>`).join('') || '<div class="mut">未配置订阅</div>';
    view.innerHTML = navHtml() + `
    <div class="card"><h2>WAF 防护状态</h2>
      <div class="row">
        <span>WAF: ${wf.enabled ? '<span class="ok">已启用</span>' : '<span class="bad">已停用</span>'}</span>
        <button class="ghost" onclick="${P}wafToggle(${!wf.enabled})">${wf.enabled ? '停用 WAF' : '启用 WAF'}</button>
        <span class="mut">改动后到「反代配置」页执行应用并 reload</span>
      </div></div>
    <div class="card"><h2>IP 黑/白名单</h2>
      <div class="row" style="margin-bottom:8px">
        <input id="ipVal" type="text" placeholder="IP 或网段，如 1.2.3.4 / 10.0.0.0/8">
        <button class="ghost" onclick="${P}wafIp('blacklist','add')">加入黑名单</button>
        <button class="ghost" onclick="${P}wafIp('whitelist','add')">加入白名单</button>
      </div>
      <table><tr><th>名单</th><th>条目</th></tr>
        <tr><td>黑名单</td><td>${wf.blacklist_ips.map(x => `<span class="row">${esc(x)} <button class="ghost" onclick="${P}wafIp('blacklist','remove','${esc(x)}')">移除</button></span>`).join(' ') || '<span class="mut">(空)</span>'}</td></tr>
        <tr><td>白名单</td><td>${wf.whitelist_ips.map(x => `<span class="row">${esc(x)} <button class="ghost" onclick="${P}wafIp('whitelist','remove','${esc(x)}')">移除</button></span>`).join(' ') || '<span class="mut">(空)</span>'}</td></tr>
      </table></div>
    <div class="card"><h2>限流（Caddy 原生 rate_limit，需 Caddy 2.9+）</h2>
      <div class="row">
        <span>状态: ${rl.enabled ? '<span class="ok">开启</span>' : '<span class="bad">关闭</span>'}</span>
        <input id="rlReq" type="text" placeholder="请求数，如 30" value="${esc(rl.requests)}">
        <input id="rlWin" type="text" placeholder="窗口，如 10s" value="${esc(rl.window)}">
        <button class="ghost" onclick="${P}rlSave()">保存并开启</button>
        <button class="ghost" onclick="${P}rlOff()">关闭</button>
      </div></div>
    <div class="card"><h2>本地规则</h2>
      <div class="row" style="margin-bottom:8px">
        <select id="ruleKind">
          <option value="path_regex">路径正则</option>
          <option value="user_agent">User-Agent 正则</option>
          <option value="header">请求头正则</option>
          <option value="method">请求方法</option>
          <option value="query">查询参数</option>
        </select>
        <input id="ruleField" type="text" placeholder="字段(header/query用)" style="min-width:120px">
        <input id="rulePattern" type="text" placeholder="pattern（正则或方法/值）" style="min-width:260px">
        <input id="ruleName" type="text" placeholder="备注(可选)" style="min-width:120px">
        <button onclick="${P}wafAddRule()">添加</button>
      </div>
      <table><tr><th>备注</th><th>类型</th><th>pattern</th><th>来源</th><th>状态</th><th></th></tr>${rules}</table></div>
    <div class="card"><h2>订阅远程 WAF 规则</h2>
      <div class="row" style="margin-bottom:8px">
        <input id="subUrl" type="text" placeholder="https://example.com/rules.json" style="min-width:320px">
        <input id="subName" type="text" placeholder="名称(可选)" style="min-width:120px">
        <input id="subInterval" type="text" placeholder="间隔秒(默认3600)" style="min-width:100px">
        <button onclick="${P}subAdd()">添加/更新</button>
        <button class="ghost" onclick="${P}subRecommended()" title="一键订阅内置推荐规则集（OWASP CRS 精选）">推荐规则</button>
      </div>
      ${sub}
      <div class="mut" style="margin-top:6px">同步后订阅规则自动合并生效；改动后到「反代配置」应用并 reload。</div>
    </div>`;
  }
  async function wafToggle(enabled) { await api('POST', '/api/caddyconf/waf', { enabled }); await wafTab(); }
  async function wafAddRule() {
    const kind = document.getElementById('ruleKind').value;
    const pattern = document.getElementById('rulePattern').value.trim();
    if (!pattern) { alert('请输入 pattern'); return; }
    await api('POST', '/api/caddyconf/waf/rules', { kind, pattern,
      field: document.getElementById('ruleField').value.trim(),
      name: document.getElementById('ruleName').value.trim() });
    await wafTab();
  }
  async function wafToggleRule(id, enabled) { await api('POST', `/api/caddyconf/waf/rules/${id}/toggle`, { enabled }); await wafTab(); }
  async function wafDelRule(id) { if (!confirm('删除规则 ' + id + ' ？')) return; await api('DELETE', `/api/caddyconf/waf/rules/${id}`); await wafTab(); }
  async function wafIp(list, action, ip) {
    ip = ip || document.getElementById('ipVal').value.trim();
    if (!ip) { alert('请输入 IP'); return; }
    await api('POST', '/api/caddyconf/waf/ips', { list, action, ip });
    await wafTab();
  }
  async function rlSave() {
    const requests = parseInt(document.getElementById('rlReq').value);
    const window = document.getElementById('rlWin').value.trim();
    await api('POST', '/api/caddyconf/waf/ratelimit', { enabled: true, requests, window });
    await wafTab();
  }
  async function rlOff() { await api('POST', '/api/caddyconf/waf/ratelimit', { enabled: false }); await wafTab(); }
  async function subAdd() {
    const url = document.getElementById('subUrl').value.trim();
    if (!url) { alert('请输入订阅 URL'); return; }
    const name = document.getElementById('subName').value.trim();
    const interval = parseInt(document.getElementById('subInterval').value) || 3600;
    await api('POST', '/api/caddyconf/waf/subscribe', { action: 'set', url, name, interval });
    await wafTab();
  }
  async function subRecommended() {
    const r = await api('POST', '/api/caddyconf/waf/subscribe/recommended', { interval: 3600 });
    const s = r.sync && r.sync.synced ? r.sync.synced[0] : null;
    if (s && s.ok) alert('已加入推荐订阅并同步 ' + s.rules + ' 条规则（跳过 ' + s.skipped + '）。执行「反代配置 → 应用并 reload」后生效。');
    else alert('已加入推荐订阅，但同步失败：' + (s && s.error || '未知错误'));
    await wafTab();
  }
  async function subSync(url) { await api('POST', '/api/caddyconf/waf/subscribe', { action: 'sync', url }); await wafTab(); }
  async function subRemove(url) {
    if (!confirm('移除订阅 ' + url + ' ？（其规则将不再生效）')) return;
    await api('POST', '/api/caddyconf/waf/subscribe', { action: 'remove', url });
    await wafTab();
  }

  function go(s) {
    section = s || 'rproxy';
    if (section === 'waf') wafTab();
    else rproxyTab();
  }

  return {
    title: 'Caddy 环境',
    sections: [
      { id: 'rproxy', title: '反代配置' }, { id: 'waf', title: 'WAF 防护' }
    ],
    go: go,
    open: function (s) { go(s || 'rproxy'); },
    rproxyTab: rproxyTab, wafTab: wafTab,
    setCaddyPort: setCaddyPort, caddyPreview: caddyPreview, caddyApply: caddyApply,
    wafToggle: wafToggle, wafAddRule: wafAddRule, wafToggleRule: wafToggleRule,
    wafDelRule: wafDelRule, wafIp: wafIp, rlSave: rlSave, rlOff: rlOff,
    subAdd: subAdd, subRecommended: subRecommended, subSync: subSync, subRemove: subRemove
  };
})();
