/* AUPS 插件：caddy — 反代配置 / Caddyfile 管理 / 实例控制
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
      <button class="${section === 'caddyfile' ? 'on' : ''}" onclick="${P}go('caddyfile')">Caddyfile 管理</button>
      <button class="${section === 'instance' ? 'on' : ''}" onclick="${P}go('instance')">实例控制</button>
    </div>`;
  }

  function errCard(e) {
    const msg = (e && e.message) || e || '未知错误';
    return `<div class="card"><h2>加载失败</h2>
      <pre style="white-space:pre-wrap">${esc(msg)}</pre>
      <div class="mut" style="margin-top:6px">请确认面板服务已重启、插件已启用（插件中心）。</div></div>`;
  }

  function go(s) {
    section = s || 'rproxy';
    if (section === 'rproxy') rproxyTab();
    else if (section === 'caddyfile') caddyfileTab();
    else if (section === 'instance') instanceTab();
  }

  /* ---------- 反代配置 ---------- */
  async function rproxyTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const [st, pt] = await Promise.all([
        api('GET', '/api/caddyconf/status'),
        api('GET', '/api/ports')
      ]);
      const listening = (pt.listening || []).map(x => `${x.local}  (${x.process})`).join('\n');
      const deploy = st.deploy === 'container'
        ? `容器 · ${esc((st.container||{}).name||'')} ${(st.container||{}).running ? '运行中' : '已停止'}`
        : `实机 · ${esc(st.reload_method || '-')}`;
      view.innerHTML = navHtml() + `
      <div class="card"><h2>反代后端 · ${esc(st.backend)}</h2>
        <div class="row">
          <span>配置: <span class="mut">${esc(st.caddyfile || '-')}</span></span>
          <span class="mut">${deploy}${st.name === 'caddy' && st.version ? ` · Caddy ${esc(st.version)}` : ''}</span>
        </div>
        <div class="row" style="margin-top:10px">
          <button class="ghost" onclick="${P}caddyPreview()">预览片段</button>
          <button onclick="${P}caddyApply()">应用并 reload</button>
        </div>
        <div class="mut" style="margin-top:10px">下载路由 + WAF 规则由面板写入 Caddyfile（AUPS APPS / AUPS WAF 标记区）。WAF 规则模板在「安全管理 → WAF 模板」维护，变更后自动重载本反代。</div>
      </div>
      <div class="card"><h2>监听端口</h2><pre>${listening || '无'}</pre></div>
      <div id="ccPreviewBox"></div>
      <div class="card"><h2>Caddy 日志</h2>
        <div class="row"><button class="ghost" onclick="${P}caddyLogs()">查看最近日志</button></div>
        <pre id="ccLogBox" style="margin-top:8px;max-height:400px;overflow:auto;color:var(--mut);font-size:12px"></pre>
      </div>`;
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }
  async function caddyPreview() {
    const box = document.getElementById('ccPreviewBox');
    const d = await api('GET', '/api/caddyconf/preview');
    box.innerHTML = `<div class="card"><h2>预览（尚未写入）</h2>
      <h2 class="mut">下载路由</h2><pre>${esc(d.apps)}</pre>
      <h2 class="mut">WAF（来自核心模板）</h2><pre>${esc(d.waf)}</pre></div>`;
  }
  async function caddyApply() { await api('POST', '/api/caddyconf/apply', { reload: true }); alert('已写入 Caddyfile 并 reload'); await rproxyTab(); }
  async function caddyLogs() {
    const box = document.getElementById('ccLogBox');
    box.textContent = '加载中...';
    try {
      const d = await api('GET', '/api/caddy/journal?lines=100');
      if (d.error) { box.textContent = d.error; return; }
      box.textContent = (d.lines || []).join('\n') || '(无日志)';
    } catch (e) { box.textContent = '加载失败: ' + ((e && e.message) || e); }
  }

  /* ---------- Caddyfile 管理（参考 caddydash） ---------- */
  let sitesCache = [];
  async function caddyfileTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const [st, cf, sites] = await Promise.all([
        api('GET', '/api/caddy/status'),
        api('GET', '/api/caddy/caddyfile'),
        api('GET', '/api/caddy/sites')
      ]);
      sitesCache = (sites.sites || []).slice();
      const deploy = st.deploy === 'container' ? '容器' : '实机';
      const rows = sitesCache.map(s => `<tr>
        <td>${esc(s.host)}</td>
        <td>${esc(s.mode)}</td>
        <td>${esc(s.target || '-')}</td>
        <td>
          <button class="ghost" onclick="${P}siteEdit('${esc(s.host)}')">编辑</button>
          <button class="ghost danger" onclick="${P}siteDelete('${esc(s.host)}')">删除</button>
        </td></tr>`).join('') || '<tr><td colspan="4" class="mut">暂无站点块</td></tr>';
      view.innerHTML = navHtml() + `
      <div class="card"><h2>Caddyfile 管理</h2>
        <div class="row"><span class="mut">配置: ${esc(cf.path)} · 部署: ${deploy}</span></div>
        <div class="row" style="margin-top:8px">
          <button onclick="${P}siteNew()">新增站点</button>
          <button class="ghost" onclick="${P}caddyfileReload()">重载配置</button>
        </div>
      </div>
      <div class="card"><h2>站点块</h2>
        <table><thead><tr><th>域名</th><th>模式</th><th>目标</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table>
      </div>
      <div class="card"><h2>完整 Caddyfile</h2>
        <textarea id="cfEditor" rows="18" style="width:100%;font-family:monospace" spellcheck="false">${esc(cf.content)}</textarea>
        <div class="row" style="margin-top:8px">
          <button onclick="${P}caddyfileSave()">保存并 reload</button>
          <button class="ghost" onclick="${P}cfPresets()">常用片段预设</button>
          <span class="mut" style="margin-left:auto">${esc(cf.lines)} 行</span>
        </div>
        <div id="cfPresetBox"></div>
      </div>
      <div id="siteModal"></div>`;
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }
  async function caddyfileReload() { await api('POST', '/api/caddy/instance/reload'); alert('已重载 Caddy'); await caddyfileTab(); }
  async function caddyfileSave() {
    const content = document.getElementById('cfEditor').value;
    try { await api('POST', '/api/caddy/caddyfile', { content, reload: true }); alert('已保存并 reload'); await caddyfileTab(); }
    catch(e){ alert('保存失败：' + ((e&&e.detail)||e)); }
  }
  async function cfPresets() {
    const d = await api('GET', '/api/caddy/presets');
    const box = document.getElementById('cfPresetBox');
    const btns = (d.presets||[]).map(p =>
      `<button class="ghost" style="margin:2px" onclick="${P}cfInsertPreset('${esc(p.id)}')">${esc(p.title)}</button>`).join('');
    box.innerHTML = `<div class="mut" style="margin-top:8px">插入常用片段：${btns}</div>`;
    window._cfPresets = d.presets || [];
  }
  function cfInsertPreset(id) {
    const p = (window._cfPresets||[]).find(x => x.id === id);
    if (!p) return;
    const ta = document.getElementById('cfEditor');
    if (!ta) return;
    ta.value = (ta.value ? ta.value.replace(/\s+$/,'') + '\n' : '') + (p.lines||[]).join('\n') + '\n';
  }
  function siteModal(html) {
    document.getElementById('siteModal').innerHTML =
      `<div class="ov-modal" style="position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:50">
        <div class="card" style="min-width:420px">${html}</div>
      </div>`;
  }
  function siteNew() {
    siteModal(`
      <h2>新增站点</h2>
      <div class="blk"><span class="mut">域名</span><input id="siteHost" placeholder="example.com"></div>
      <div class="blk"><span class="mut">模式</span>
        <select id="siteMode">
          <option value="reverse_proxy">反向代理</option>
          <option value="file_server">文件服务</option>
        </select></div>
      <div class="blk"><span class="mut">目标</span><input id="siteTarget" placeholder="反向代理: localhost:8080 / 文件服务: /var/www"></div>
      <div class="blk"><span class="mut">额外指令（可选）</span><textarea id="siteExtra" rows="3" style="width:100%"></textarea></div>
      <div class="row" style="margin-top:10px">
        <button onclick="${P}siteCreate()">创建</button>
        <button class="ghost" onclick="${P}siteClose()">取消</button>
      </div>`);
  }
  async function siteCreate() {
    const host = document.getElementById('siteHost').value.trim();
    const mode = document.getElementById('siteMode').value;
    const target = document.getElementById('siteTarget').value.trim();
    const extra = document.getElementById('siteExtra').value;
    try { await api('POST', '/api/caddy/sites', { host, mode, target, extra }); alert('已创建'); await caddyfileTab(); }
    catch(e){ alert('创建失败：' + ((e&&e.detail)||e)); }
  }
  async function siteEdit(host) {
    const s = sitesCache.find(x => x.host === host);
    if (!s) return;
    siteModal(`
      <h2>编辑站点 · ${esc(host)}</h2>
      <div class="blk"><span class="mut">模式</span>
        <select id="siteMode">
          <option value="reverse_proxy" ${s.mode==='reverse_proxy'?'selected':''}>反向代理</option>
          <option value="file_server" ${s.mode==='file_server'?'selected':''}>文件服务</option>
        </select></div>
      <div class="blk"><span class="mut">目标</span><input id="siteTarget" value="${esc(s.target||'')}" placeholder="反向代理: localhost:8080 / 文件服务: /var/www"></div>
      <div class="blk"><span class="mut">额外指令（可选，留空保留原自定义行）</span><textarea id="siteExtra" rows="3" style="width:100%">${esc(s.body||'')}</textarea></div>
      <div class="row" style="margin-top:10px">
        <button onclick="${P}siteUpdate('${esc(host)}')">保存</button>
        <button class="ghost" onclick="${P}siteClose()">取消</button>
      </div>`);
  }
  async function siteUpdate(host) {
    const mode = document.getElementById('siteMode').value;
    const target = document.getElementById('siteTarget').value.trim();
    const extra = document.getElementById('siteExtra').value;
    try {
      await api('PUT', '/api/caddy/sites/' + encodeURIComponent(host), { mode, target, extra });
      // 直接更新本地缓存 + 表格行，避免全量刷新时 GET 被浏览器缓存
      const cached = sitesCache.find(s => s.host === host);
      if (cached) { cached.mode = mode; cached.target = target; }
      siteClose();
      // 重绘站点表格（不重新请求 API）
      const rows = sitesCache.map(s => `<tr>
        <td>${esc(s.host)}</td>
        <td>${esc(s.mode)}</td>
        <td>${esc(s.target || '-')}</td>
        <td>
          <button class="ghost" onclick="${P}siteEdit('${esc(s.host)}')">编辑</button>
          <button class="ghost danger" onclick="${P}siteDelete('${esc(s.host)}')">删除</button>
        </td></tr>`).join('') || '<tr><td colspan="4" class="mut">暂无站点块</td></tr>';
      document.querySelectorAll('table tbody').forEach(t => { t.innerHTML = rows; });
    } catch(e){ alert('保存失败：' + ((e&&e.detail)||e)); }
  }
  async function siteDelete(host) {
    if (!confirm('删除站点 ' + host + ' ？')) return;
    try { await api('DELETE', '/api/caddy/sites/' + encodeURIComponent(host)); alert('已删除'); await caddyfileTab(); }
    catch(e){ alert('删除失败：' + ((e&&e.detail)||e)); }
  }
  function siteClose() { document.getElementById('siteModal').innerHTML = ''; }

  /* ---------- 实例控制 ---------- */
  async function instanceTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const [st, cs] = await Promise.all([
        api('GET', '/api/caddyconf/status'),
        api('GET', '/api/caddy/status')
      ]);
      const c = cs.container || {};
      const deployHtml = cs.deploy === 'container'
        ? `容器 <b>${esc(c.name||'-')}</b> · ${esc(c.runtime||'-')} · ${esc(c.image||'-')} · ${c.exists ? (c.running ? '<b style="color:var(--ok)">运行中</b>' : '<b style="color:var(--err)">已停止</b>') : '<span class="mut">未创建</span>'}`
        : `实机 · reload: ${esc(st.reload_method || '-')}${st.version ? ' · Caddy ' + esc(st.version) : ''}`;
      const installBtn = (!cs.installed && cs.deploy !== 'container')
        ? `<div class="row" style="margin-top:12px;padding:10px;border:1px solid var(--err);border-radius:6px">
             <span style="color:var(--err)">Caddy 未安装</span>
             <button onclick="${P}caddyInstall()" style="margin-left:auto">安装 Caddy</button>
           </div>`
        : '';
      view.innerHTML = navHtml() + `
      <div class="card"><h2>实例控制</h2>
        <div class="row"><span class="mut">部署: ${deployHtml}</span></div>
        ${installBtn}
        <div class="row" style="margin-top:12px">
          <button onclick="${P}inst('stop')">停止</button>
          <button onclick="${P}inst('restart')">重启</button>
          <button onclick="${P}inst('reload')">重载</button>
        </div>
        <div class="mut" style="margin-top:8px">停止后下载/WAF 站点将不可用；重载用于应用 Caddyfile 改动。</div>
      </div>`;
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }
  async function caddyInstall() {
    if (!confirm('安装 Caddy？将通过系统包管理器安装并部署到面板目录。')) return;
    try {
      const r = await api('POST', '/api/caddy/install');
      alert('Caddy 已安装: ' + (r.message || ''));
      await instanceTab();
    } catch (e) { alert('安装失败: ' + ((e && e.detail) || e)); }
  }
  async function inst(action) {
    const names = { stop:'停止', restart:'重启', reload:'重载' };
    if (action === 'stop' && !confirm('确定停止 Caddy 服务？')) return;
    try { const r = await api('POST', '/api/caddy/instance/' + action); alert('已' + (names[action]||action) + (r.deploy === 'container' ? '（容器）' : '')); await instanceTab(); }
    catch(e){ alert((names[action]||action) + '失败：' + ((e&&e.detail)||e)); }
  }

  return {
    title: 'Caddy 环境',
    sections: [
      { id: 'rproxy', title: '反代配置' },
      { id: 'caddyfile', title: 'Caddyfile 管理' },
      { id: 'instance', title: '实例控制' },
    ],
    go: go,
    open: function (s) { go(s || 'rproxy'); },
    rproxyTab: rproxyTab,
    caddyPreview: caddyPreview, caddyApply: caddyApply, caddyLogs: caddyLogs,
    caddyfileTab: caddyfileTab, siteNew: siteNew, siteEdit: siteEdit,
    siteUpdate: siteUpdate, siteDelete: siteDelete, siteCreate: siteCreate, siteClose: siteClose,
    caddyfileSave: caddyfileSave, caddyfileReload: caddyfileReload,
    cfPresets: cfPresets, cfInsertPreset: cfInsertPreset,
    instanceTab: instanceTab, inst: inst, caddyInstall: caddyInstall,
  };
})();