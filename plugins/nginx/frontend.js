/* AUPS 插件：nginx —— 站点管理 / 实例控制（UI 与 caddy 插件对齐）
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 * v1.3.0：站点管理（反代/文件服务、TLS、下载路由开关）、nginx.conf 编辑、
 *         实例控制（启停/重载/部署方式切换/日志），替换原单页状态视图。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['nginx'] = (function () {
  const P = 'AUPS_PLUGINS.nginx.';
  let section = 'sites';
  let sitesCache = [];
  let currentDeploy = 'host';

  function navHtml() {
    return `<div class="secnav">
      <button class="${section === 'sites' ? 'on' : ''}" onclick="${P}go('sites')">站点管理</button>
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
    section = s || 'sites';
    if (section === 'sites') sitesTab();
    else if (section === 'instance') instanceTab();
  }

  /* ---------- 站点管理 ---------- */
  async function sitesTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const [st, sites, cf] = await Promise.all([
        api('GET', '/api/nginx/status'),
        api('GET', '/api/nginx/sites').catch(() => ({ sites: [] })),
        api('GET', '/api/nginx/config').catch(() => ({ content: '', path: '' }))
      ]);
      sitesCache = sites.sites || [];
      currentDeploy = st.method || 'host';
      const rows = sitesCache.map(s => {
        const routes = (s.options || {}).download_routes
          ? '<span class="ok">开</span>' : '<span class="mut">-</span>';
        const managed = s.aups_app ? ' <span class="mut" style="font-size:11px">应用托管</span>' : '';
        return `<tr>
          <td>${esc(s.host)}${managed}</td>
          <td>${s.mode === 'file_server' ? '文件服务' : '反向代理'}</td>
          <td class="mut" style="font-size:12px">${esc(s.target || '-')}</td>
          <td>${routes}</td>
          <td>
            <button class="ghost" onclick="${P}siteEdit('${esc(s.host)}')">编辑</button>
            <button class="ghost danger" onclick="${P}siteDelete('${esc(s.host)}')">删除</button>
          </td></tr>`;
      }).join('') || '<tr><td colspan="5" class="mut">暂无站点。新增文件服务站点并开启「下载路由」即可承接 appupdate 短链。</td></tr>';
      view.innerHTML = navHtml() + `
      <div class="card"><h2>站点管理</h2>
        <div class="row"><span class="mut">部署: ${currentDeploy === 'container' ? '容器' : '实机'}${st.version ? ' · ' + esc(st.version) : ''}</span></div>
        <div class="row" style="margin-top:8px">
          <button onclick="${P}siteNew()">新增站点</button>
          <button class="ghost" onclick="${P}sitesReload()">重载配置</button>
        </div>
      </div>
      <div class="card"><h2>站点列表</h2>
        <table><thead><tr><th>域名</th><th>模式</th><th>目标</th><th>下载路由</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table>
        <div class="mut" style="margin-top:8px">「下载路由」：在该文件服务站点内注入 appupdate 托管短链（/应用/latest 按文件日期指向最新包），数据来自应用更新管理插件。</div>
      </div>
      <div class="card"><h2>nginx.conf</h2>
        <textarea id="ngConfEditor" rows="16" style="width:100%;font-family:monospace" spellcheck="false">${esc(cf.content || '')}</textarea>
        <div class="row" style="margin-top:8px">
          <button onclick="${P}confSave()">保存并校验</button>
          <span class="mut" style="margin-left:auto">${esc((cf.content || '').split('\n').length)} 行 · ${esc(cf.path || '')}</span>
        </div>
      </div>
      <div id="siteModal"></div>`;
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }

  const PRESETS = [
    { id: 'gzip', title: 'gzip 压缩', lines: ['gzip on;', 'gzip_types text/plain text/css application/javascript application/json;'] },
    { id: 'headers', title: '安全响应头', lines: ['add_header X-Content-Type-Options nosniff;', 'add_header X-Frame-Options DENY;', 'add_header Referrer-Policy no-referrer;'] },
    { id: 'cache', title: '静态资源缓存', lines: ['location ~* \\.(jpg|png|gif|css|js)$ { expires 1d; }'] },
  ];

  function siteModal(html) {
    document.getElementById('siteModal').innerHTML =
      `<div class="ov-modal" style="position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:50">
        <div class="card" style="min-width:440px;max-height:90vh;overflow:auto">${html}</div>
      </div>`;
  }

  function siteOptionsHtml(o) {
    const tls = (o && o.tls) || {};
    return `
      <div class="blk"><span class="mut">TLS 证书路径（可选，两者都填启用 443 ssl）</span>
        <input id="siteTlsCert" value="${esc(tls.cert || '')}" placeholder="/etc/letsencrypt/live/xxx/fullchain.pem" style="margin-top:4px">
        <input id="siteTlsKey" value="${esc(tls.key || '')}" placeholder="/etc/letsencrypt/live/xxx/privkey.pem" style="margin-top:4px">
        <div class="mut" style="font-size:11px;margin-top:4px">证书申请请使用「certbot」或「acme」插件</div>
      </div>
      <div class="blk"><label><input type="checkbox" id="siteWs" ${!(o && o.websocket === false) ? 'checked' : ''}> 反向代理支持 WebSocket</label></div>
      <div class="blk"><label><input type="checkbox" id="siteRoutes" ${(o || {}).download_routes ? 'checked' : ''}> 下载路由（appupdate 托管短链，latest 按文件日期）</label></div>`;
  }

  function readSiteOptions() {
    const o = {};
    const cert = document.getElementById('siteTlsCert').value.trim();
    const key = document.getElementById('siteTlsKey').value.trim();
    if (cert && key) o.tls = { cert, key };
    o.websocket = document.getElementById('siteWs').checked;
    o.download_routes = document.getElementById('siteRoutes').checked;
    return o;
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
      <div class="blk"><span class="mut">目标</span><input id="siteTarget" placeholder="反向代理: 127.0.0.1:8080 / 文件服务: /var/www/html"></div>
      ${siteOptionsHtml({})}
      <div class="blk"><span class="mut">额外指令（可选，插入 server 块）</span><textarea id="siteExtra" rows="3" style="width:100%"></textarea>
        <div id="sitePresets" style="margin-top:4px"></div></div>
      <div class="row" style="margin-top:10px">
        <button onclick="${P}siteCreate()">创建</button>
        <button class="ghost" onclick="${P}siteClose()">取消</button>
      </div>`);
    renderPresets('sitePresets');
  }

  function renderPresets(boxId) {
    const box = document.getElementById(boxId);
    if (!box) return;
    box.innerHTML = `<span class="mut" style="font-size:12px">插入片段：</span>` + PRESETS.map(p =>
      `<button class="ghost" style="margin:2px;font-size:12px" onclick="${P}insertPreset('${p.id}')">${p.title}</button>`).join('');
  }

  function insertPreset(id) {
    const p = PRESETS.find(x => x.id === id);
    const ta = document.getElementById('siteExtra');
    if (!p || !ta) return;
    ta.value = (ta.value ? ta.value.replace(/\s+$/, '') + '\n' : '') + p.lines.join('\n') + '\n';
  }

  async function siteCreate() {
    const host = document.getElementById('siteHost').value.trim();
    const mode = document.getElementById('siteMode').value;
    const target = document.getElementById('siteTarget').value.trim();
    const extra = document.getElementById('siteExtra').value;
    const options = readSiteOptions();
    try { await api('POST', '/api/nginx/sites', { host, mode, target, extra, options }); alert('已创建'); await sitesTab(); }
    catch (e) { alert('创建失败：' + ((e && e.detail) || e)); }
  }

  function siteEdit(host) {
    const s = sitesCache.find(x => x.host === host);
    if (!s) return;
    siteModal(`
      <h2>编辑站点 · ${esc(host)}</h2>
      <div class="blk"><span class="mut">模式</span>
        <select id="siteMode">
          <option value="reverse_proxy" ${s.mode !== 'file_server' ? 'selected' : ''}>反向代理</option>
          <option value="file_server" ${s.mode === 'file_server' ? 'selected' : ''}>文件服务</option>
        </select></div>
      <div class="blk"><span class="mut">目标</span><input id="siteTarget" value="${esc(s.target || '')}" placeholder="反向代理: 127.0.0.1:8080 / 文件服务: /var/www/html"></div>
      ${siteOptionsHtml(s.options || {})}
      <div class="blk"><span class="mut">额外指令（可选，留空保留原自定义行）</span><textarea id="siteExtra" rows="3" style="width:100%">${esc(extraOf(s))}</textarea>
        <div id="sitePresets" style="margin-top:4px"></div></div>
      <div class="row" style="margin-top:10px">
        <button onclick="${P}siteUpdate('${esc(host)}')">保存</button>
        <button class="ghost" onclick="${P}siteClose()">取消</button>
      </div>`);
    renderPresets('sitePresets');
  }

  function extraOf(s) {
    // 托管域名校验行不属于用户可编辑内容
    return (s.extra || '').split('\n').filter(l => !/aups-domain-check/.test(l)).join('\n');
  }

  async function siteUpdate(host) {
    const mode = document.getElementById('siteMode').value;
    const target = document.getElementById('siteTarget').value.trim();
    const extra = document.getElementById('siteExtra').value;
    const options = readSiteOptions();
    try {
      await api('PUT', '/api/nginx/sites/' + encodeURIComponent(host), { mode, target, extra, options });
      alert('已保存'); await sitesTab();
    } catch (e) { alert('保存失败：' + ((e && e.detail) || e)); }
  }

  async function siteDelete(host) {
    if (!confirm('删除站点 ' + host + ' ？')) return;
    try { await api('DELETE', '/api/nginx/sites/' + encodeURIComponent(host)); alert('已删除'); await sitesTab(); }
    catch (e) { alert('删除失败：' + ((e && e.detail) || e)); }
  }

  function siteClose() { document.getElementById('siteModal').innerHTML = ''; }

  async function sitesReload() {
    try { await api('POST', '/api/nginx/instance/reload', {}, true); alert('已重载 nginx'); }
    catch (e) { alert('重载失败：' + ((e && e.detail) || e)); }
    await sitesTab();
  }

  async function confSave() {
    const content = document.getElementById('ngConfEditor').value;
    try { await api('POST', '/api/nginx/config', { content, reload: true }); alert('已保存并重载'); await sitesTab(); }
    catch (e) { alert('保存失败：' + ((e && e.detail) || e)); }
  }

  /* ---------- 实例控制 ---------- */
  async function instanceTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const st = await api('GET', '/api/nginx/status');
      currentDeploy = st.method || 'host';
      const running = st.running
        ? '<b style="color:var(--ok)">运行中</b>' : '<b style="color:var(--bad)">未运行</b>';
      const dirs = `
        <tr><td>runtime（软件）</td><td class="mut">${esc(st.runtime_dir || '-')}</td></tr>
        <tr><td>config（配置）</td><td class="mut">${esc(st.config_dir || '-')}</td></tr>
        <tr><td>data（数据）</td><td class="mut">${esc(st.data_dir || '-')}</td></tr>`;
      view.innerHTML = navHtml() + `
      <div class="card"><h2>实例状态</h2>
        <div class="row"><span class="mut">部署: ${currentDeploy === 'container' ? '容器' : '实机'} · ${running} · ${esc(st.version || '未安装')}</span></div>
        <div class="row" style="margin-top:12px">
          <button onclick="${P}inst('start')">启动</button>
          <button onclick="${P}inst('stop')">停止</button>
          <button onclick="${P}inst('restart')">重启</button>
          <button onclick="${P}inst('reload')">重载</button>
          <button class="ghost" onclick="${P}instanceTab()" style="margin-left:auto">刷新状态</button>
        </div>
        ${st.installed ? '' : `<div class="row" style="margin-top:12px;padding:10px;border:1px solid var(--bad);border-radius:6px">
          <span style="color:var(--bad)">${currentDeploy === 'container' ? 'nginx 容器尚未创建' : 'nginx 未部署'}</span>
          <button onclick="${P}nginxInstall()" style="margin-left:auto">安装/部署</button></div>`}
      </div>
      <div class="card"><h2>部署方式</h2>
        <div class="row">
          <select id="ngDeploy">
            <option value="host" ${currentDeploy === 'host' ? 'selected' : ''}>实机</option>
            <option value="container" ${currentDeploy === 'container' ? 'selected' : ''}>容器</option>
          </select>
          <select id="ngRuntime"><option value="docker">Docker</option><option value="podman">Podman</option></select>
          <button class="ghost" onclick="${P}deploy()">切换部署</button>
          <span class="mut" style="font-size:12px">切换后配置与数据目录保持不变</span>
        </div>
      </div>
      <div class="card"><h2>部署目录（面板目录下）</h2>
        <table><tr><th>类别</th><th>路径</th></tr>${dirs}</table>
        <div class="mut" style="margin-top:8px">证书申请请使用「certbot」或「acme」插件。</div></div>
      <div class="card"><h2>日志</h2>
        <div class="row">
          <button class="ghost" onclick="${P}nginxLogs('access')">访问日志</button>
          <button class="ghost" onclick="${P}nginxLogs('error')">错误日志</button>
          <span class="mut" style="font-size:12px;margin-left:8px">最近 100 行</span>
        </div>
        <pre id="ngLogBox" style="margin-top:8px;max-height:400px;overflow:auto;color:var(--mut);font-size:12px">点击上方按钮查看</pre>
      </div>`;
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }

  async function inst(action) {
    const names = { start: '启动', stop: '停止', restart: '重启', reload: '重载' };
    if (action === 'stop' && !confirm('确定停止 nginx 服务？')) return;
    try { await api('POST', '/api/nginx/instance/' + action, {}, true); alert('已' + (names[action] || action)); await instanceTab(); }
    catch (e) { alert((names[action] || action) + '失败：' + ((e && e.detail) || e)); }
  }

  async function nginxLogs(kind) {
    const box = document.getElementById('ngLogBox');
    if (!box) return;
    box.textContent = '加载中...';
    try {
      const d = await api('GET', '/api/nginx/logs?kind=' + kind + '&limit=100');
      box.textContent = (d.lines || []).join('\n') || '(无日志)';
    } catch (e) { box.textContent = '加载失败: ' + ((e && e.message) || e); }
  }

  async function nginxInstall() {
    if (!confirm('安装/部署 nginx？（系统已装时复用其二进制并迁移配置）')) return;
    try { const r = await api('POST', '/api/nginx/install'); alert(r.message || '已安装'); await instanceTab(); }
    catch (e) { alert('安装失败：' + ((e && e.detail) || e)); }
  }

  async function deploy() {
    const method = document.getElementById('ngDeploy').value;
    const runtime = document.getElementById('ngRuntime').value;
    if (!confirm('切换部署方式为「' + (method === 'container' ? '容器' : '实机') + '」？将重建 nginx 实例。')) return;
    try { await api('POST', '/api/nginx/deploy', { method, runtime }); alert('已切换'); await instanceTab(); }
    catch (e) { alert('切换失败：' + ((e && e.detail) || e)); }
  }

  return {
    title: 'Nginx 环境',
    sections: [
      { id: 'sites', title: '站点管理' },
      { id: 'instance', title: '实例控制' },
    ],
    go: go,
    open: function (s) { go(s || 'sites'); },
    sitesTab: sitesTab, siteNew: siteNew, siteEdit: siteEdit, siteCreate: siteCreate,
    siteUpdate: siteUpdate, siteDelete: siteDelete, siteClose: siteClose,
    sitesReload: sitesReload, confSave: confSave, insertPreset: insertPreset,
    instanceTab: instanceTab, inst: inst, nginxLogs: nginxLogs,
    nginxInstall: nginxInstall, deploy: deploy,
  };
})();
