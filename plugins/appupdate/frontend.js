/* AUPS 插件：appupdate — 应用注册 / 部署配置 / CI 用户 / 存储与版本
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['appupdate'] = (function () {
  const P = 'AUPS_PLUGINS.appupdate.';
  let section = 'apps';
  let appsCache = [];
  let usersCache = [];
  let proxyCache = [];
  let appsBaseDir = '/var/www/html';

  function navHtml() {
    return `<div class="secnav">
      <button class="${section === 'apps' ? 'on' : ''}" onclick="${P}go('apps')">应用管理</button>
      <button class="${section === 'users' ? 'on' : ''}" onclick="${P}go('users')">CI 用户</button>
      <button class="${section === 'storage' ? 'on' : ''}" onclick="${P}go('storage')">存储与版本</button>
    </div>`;
  }

  function errCard(e) {
    const msg = (e && e.message) || e || '未知错误';
    return `<div class="card"><h2>加载失败</h2><pre style="white-space:pre-wrap">${esc(msg)}</pre></div>`;
  }

  function go(s) {
    section = s || 'apps';
    if (section === 'apps') appsTab();
    else if (section === 'users') usersTab();
    else if (section === 'storage') storageTab();
  }

  function fmtSize(b) {
    if (!b) return '0 B';
    const u = ['B', 'KB', 'MB', 'GB'];
    let i = 0; let s = b;
    while (s >= 1024 && i < u.length - 1) { s /= 1024; i++; }
    return s.toFixed(i ? 1 : 0) + ' ' + u[i];
  }

  function modal(html) {
    document.getElementById('appModal').innerHTML =
      `<div class="ov-modal" style="position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:50">
        <div class="card" style="min-width:520px;max-width:90vw;max-height:85vh;overflow:auto">${html}</div>
      </div>`;
  }
  function modalClose() { const m = document.getElementById('appModal'); if (m) m.innerHTML = ''; }

  /* ---------- 共享弹窗：新增/编辑应用 ---------- */
  function appModalHtml(name, data) {
    // GET /api/apps/{name} 返回应用基础信息，部署字段位于 deploy 子对象。
    // 弹窗使用扁平字段渲染，编辑时需解包，同时保留顶层 dir/name 等信息。
    const raw = data || {};
    const d = Object.assign({}, raw, raw.deploy || {});
    const ssl = d.ssl || {};
    const isNew = !name;
    // 已注册域名列表（排除当前应用）
    const domainMap = new Map();
    appsCache.filter(a => a.deploy && a.deploy.domain && a.name !== name).forEach(a => {
      const domain = String(a.deploy.domain).trim().replace(/\.$/, '');
      if (domain && !domainMap.has(domain.toLowerCase())) domainMap.set(domain.toLowerCase(), domain);
    });
    const domains = [...domainMap.values()];
    const domainListHtml = domains.length
      ? `<div class="mut" style="font-size:11px;margin-top:4px">已有域名：${domains.map(dom => `<span style="cursor:pointer;color:var(--acc);margin:0 4px" onclick="document.getElementById('${isNew?'n':'e'}Domain').value='${esc(dom)}'">${esc(dom)}</span>`).join('')}</div>`
      : '';
    const ports = [...new Set(appsCache.filter(a => a.deploy && a.deploy.port && a.name !== name)
      .map(a => Number(a.deploy.port)).filter(Boolean))].sort((a, b) => a - b);
    const portListHtml = ports.length
      ? `<div class="mut" style="font-size:11px;margin-top:4px">已注册端口：${ports.map(port => `<span style="margin:0 4px">${port}</span>`).join('')}</div>`
      : '';
    // CI 用户下拉
    const userOpts = usersCache.map(u =>
      `<option value="${esc(u.name)}" ${d.ci_user===u.name?'selected':''}>${esc(u.name)}${u.comment ? ' ('+esc(u.comment)+')' : ''}</option>`
    ).join('');
    // 反代插件下拉
    const proxyOpts = proxyCache.map(p =>
      `<option value="${esc(p)}" ${d.proxy===p?'selected':''}>${esc(p)}</option>`
    ).join('');
    // SSL 子选项
    const sslMode = ssl.mode || 'none';
    let sslSubHtml = '';
    if (sslMode === 'manual') {
      const sslType = ssl.type || 'text';
      sslSubHtml = `
        <div class="blk"><span class="mut">证书格式</span>
          <select id="${isNew?'n':'e'}SslType" onchange="${P}toggleSslType()">
            <option value="text" ${sslType==='text'?'selected':''}>粘贴证书/密钥</option>
            <option value="path" ${sslType==='path'?'selected':''}>指定证书/密钥路径</option>
          </select></div>
        <div id="sslTextInputs" style="display:${sslType==='text'?'block':'none'}">
          <div class="blk"><span class="mut">证书内容</span>
            <textarea id="${isNew?'n':'e'}SslCert" rows="3" style="width:100%;font-size:11px;font-family:monospace" placeholder="-----BEGIN CERTIFICATE-----...">${esc(ssl.cert || '')}</textarea></div>
          <div class="blk"><span class="mut">密钥内容</span>
            <textarea id="${isNew?'n':'e'}SslKey" rows="3" style="width:100%;font-size:11px;font-family:monospace" placeholder="-----BEGIN PRIVATE KEY-----...">${esc(ssl.key || '')}</textarea></div>
        </div>
        <div id="sslPathInputs" style="display:${sslType==='path'?'block':'none'}">
          <div class="blk"><span class="mut">证书路径</span>
            <input id="${isNew?'n':'e'}SslCertPath" value="${esc(ssl.cert_path || '')}" placeholder="/etc/letsencrypt/live/example.com/fullchain.pem"></div>
          <div class="blk"><span class="mut">密钥路径</span>
            <input id="${isNew?'n':'e'}SslKeyPath" value="${esc(ssl.key_path || '')}" placeholder="/etc/letsencrypt/live/example.com/privkey.pem"></div>
        </div>`;
    } else if (sslMode === 'auto') {
      sslSubHtml = `<div class="mut" style="font-size:11px;margin-top:4px">将通过所选反代插件自动申请 Let's Encrypt 证书</div>`;
    }
    const prefix = isNew ? 'n' : 'e';
    return `
      <h2>${isNew ? '新增应用' : '编辑部署配置 · ' + esc(name)}</h2>
      ${isNew ? `<div class="blk"><span class="mut">应用名称 *</span>
        <input id="nName" placeholder="myapp（字母数字._-）" oninput="${P}updateDefaultWorkdir()"></div>` : ''}
      <div class="blk"><span class="mut">域名</span>
        <input id="${prefix}Domain" value="${esc(d.domain || '')}" placeholder="example.com">
        ${domainListHtml}
        <div class="row" style="margin-top:4px">
          <button class="ghost" onclick="${P}checkDomain('${esc(name || '')}')" type="button" style="font-size:11px">校验域名</button>
          <span id="domainCheckResult" class="mut" style="font-size:11px"></span>
        </div>
      </div>
      <div class="blk"><span class="mut">反代插件</span>
        <select id="${prefix}Proxy">
          <option value="">-- 自动检测 --</option>${proxyOpts}
        </select></div>
      <div class="blk"><span class="mut">SSL</span>
        <select id="${prefix}SslMode" onchange="${P}toggleSslMode()">
          <option value="none" ${sslMode==='none'?'selected':''}>无</option>
          <option value="auto" ${sslMode==='auto'?'selected':''}>自动申请</option>
          <option value="manual" ${sslMode==='manual'?'selected':''}>手动指定</option>
        </select></div>
      <div id="sslSubOptions">${sslSubHtml}</div>
      <div class="blk"><span class="mut">服务端口</span>
        <input id="${prefix}Port" type="number" value="${d.port || ''}" placeholder="8080">
        ${portListHtml}</div>
      <div class="blk"><span class="mut">工作目录</span>
        <input id="${prefix}Workdir" value="${esc(d.workdir || (!isNew ? d.dir || '' : ''))}"
          placeholder="${esc(isNew ? appsBaseDir.replace(/\/$/, '') + '/<应用名称>' : d.dir || '')}"
          ${isNew ? `data-auto="1" oninput="this.dataset.auto='0'"` : ''}></div>
      <div class="blk"><span class="mut">CI 用户</span>
        <select id="${prefix}CiUser">
          <option value="">-- 不指定 --</option>${userOpts}
        </select>
        <div class="mut" style="font-size:11px;margin-top:4px">选择后将自动授予该用户对工作目录的读写权限</div>
      </div>
      <div class="row" style="margin-top:12px">
        <button onclick="${P}saveApp('${esc(name || '')}')">${isNew ? '新增' : '保存并授权'}</button>
        <button class="ghost" onclick="${P}modalClose()">取消</button>
      </div>`;
  }

  /* ---------- 应用管理 ---------- */
  async function appsTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const [d, ud, pd] = await Promise.all([
        api('GET', '/api/apps'),
        api('GET', '/api/users').catch(() => ({users:[]})),
        api('GET', '/api/apps/proxy-list').catch(() => ({proxies:[]})),
      ]);
      appsCache = d.apps || [];
      appsBaseDir = d.base_dir || '/var/www/html';
      usersCache = ud.users || [];
      proxyCache = pd.proxies || [];
      const rows = appsCache.map(a => {
        const dep = a.deploy || {};
        return `<tr>
          <td><b>${esc(a.name)}</b><div class="mut" style="font-size:11px">${esc(a.comment || '')}</div></td>
          <td class="mut" style="font-size:12px">${esc(dep.domain || '-')}</td>
          <td class="mut">${dep.port || '-'}</td>
          <td class="mut" style="font-size:12px">${esc(dep.workdir || a.dir)}</td>
          <td class="mut">${esc(dep.ci_user || '-')}</td>
          <td>
            <button class="ghost" onclick="${P}editApp('${esc(a.name)}')">编辑</button>
            <button class="ghost danger" onclick="${P}appDelete('${esc(a.name)}')">删除</button>
          </td></tr>`;
      }).join('');
      view.innerHTML = navHtml() + `
      <div class="card"><h2>应用列表</h2>
        <table><thead><tr><th>应用</th><th>域名</th><th>端口</th><th>目录</th><th>CI 用户</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="6" class="mut">暂无应用</td></tr>'}</tbody></table>
        <div class="row" style="margin-top:10px">
          <button onclick="${P}addApp()">新增应用</button>
          <button class="ghost" onclick="${P}appsCaddy()">同步反代路由</button>
        </div>
      </div>
      <div id="appModal"></div>`;
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }

  async function addApp() { modal(appModalHtml(null, {})); }

  async function saveApp(name) {
    const isNew = !name;
    const prefix = isNew ? 'n' : 'e';
    const appName = isNew ? document.getElementById('nName').value.trim() : name;
    if (isNew && !appName) { alert('请输入应用名称'); return; }
    const domain = document.getElementById(prefix + 'Domain').value.trim();
    const port = parseInt(document.getElementById(prefix + 'Port').value) || 0;
    const workdir = document.getElementById(prefix + 'Workdir').value.trim() || undefined;
    const ciUser = document.getElementById(prefix + 'CiUser').value;
    const proxy = document.getElementById(prefix + 'Proxy').value;
    const sslMode = document.getElementById(prefix + 'SslMode').value;
    // 构建 SSL 配置
    let ssl = { mode: sslMode };
    if (sslMode === 'manual') {
      const sslType = document.getElementById(prefix + 'SslType') ? document.getElementById(prefix + 'SslType').value : 'text';
      ssl.type = sslType;
      if (sslType === 'text') {
        ssl.cert = (document.getElementById(prefix + 'SslCert') || {}).value || '';
        ssl.key = (document.getElementById(prefix + 'SslKey') || {}).value || '';
      } else {
        ssl.cert_path = (document.getElementById(prefix + 'SslCertPath') || {}).value || '';
        ssl.key_path = (document.getElementById(prefix + 'SslKeyPath') || {}).value || '';
      }
    }
    // 前端校验
    if (!domain) { alert('请填写域名'); return; }
    if (sslMode === 'manual') {
      if (ssl.type === 'text' && (!ssl.cert || !ssl.key)) { alert('请填写证书和密钥内容'); return; }
      if (ssl.type === 'path' && (!ssl.cert_path || !ssl.key_path)) { alert('请填写证书和密钥路径'); return; }
    }
    try {
      if (isNew) {
        await api('POST', '/api/apps', { name: appName }, true);
      }
      const body = { domain, ssl, port, workdir, ci_user: ciUser, proxy: proxy || undefined };
      await api('POST', '/api/apps/' + encodeURIComponent(appName) + '/deploy', body, true);
      modalClose(); await appsTab();
    } catch(e) { alert((isNew ? '新增' : '保存') + '失败：' + ((e&&e.detail)||e)); }
  }

  async function editApp(name) {
    try {
      const app = await api('GET', '/api/apps/' + encodeURIComponent(name));
      modal(appModalHtml(name, app));
    } catch(e) { alert('加载失败：' + ((e&&e.detail)||e)); }
  }

  function updateDefaultWorkdir() {
    const nameEl = document.getElementById('nName');
    const dirEl = document.getElementById('nWorkdir');
    if (!nameEl || !dirEl || dirEl.dataset.auto === '0') return;
    const name = nameEl.value.trim().toLowerCase();
    dirEl.value = name ? appsBaseDir.replace(/\/$/, '') + '/' + name : '';
  }

  function toggleSslMode() {
    // SSL 子选项切换由 saveApp 统一处理，此处无需额外逻辑
  }

  function toggleSslType() {
    const type = (document.getElementById('nSslType') || document.getElementById('eSslType') || {}).value;
    const textEl = document.getElementById('sslTextInputs');
    const pathEl = document.getElementById('sslPathInputs');
    if (textEl) textEl.style.display = type === 'text' ? 'block' : 'none';
    if (pathEl) pathEl.style.display = type === 'path' ? 'block' : 'none';
  }

  async function checkDomain(name) {
    const domain = (document.getElementById('nDomain') || document.getElementById('eDomain') || {}).value || '';
    const workdir = (document.getElementById('nWorkdir') || document.getElementById('eWorkdir') || {}).value || '';
    const appName = name || ((document.getElementById('nName') || {}).value || '').trim();
    const resultEl = document.getElementById('domainCheckResult');
    if (!domain) { resultEl.innerHTML = '<span class="bad">请输入域名</span>'; return; }
    resultEl.innerHTML = '<span class="mut">校验中...</span>';
    try {
      const r = await api('POST', '/api/apps/validate-domain', { name: appName, domain, workdir });
      resultEl.innerHTML = r.ok
        ? `<span class="ok">${esc(r.message)}</span>`
        : `<span class="bad">${esc(r.message)}</span>`;
    } catch(e) {
      resultEl.innerHTML = `<span class="bad">校验失败：${esc((e&&e.message)||e)}</span>`;
    }
  }

  async function appDelete(name) {
    if (!confirm('删除应用 ' + name + '？（仅取消注册，不删除文件）')) return;
    try { await api('DELETE', '/api/apps/' + encodeURIComponent(name, true), null, true); await appsTab(); }
    catch(e){ alert('删除失败：' + ((e&&e.detail)||e)); }
  }

  async function appsCaddy() {
    try { await api('POST', '/api/apps/caddy', { reload: true }, true); alert('反代路由已更新'); }
    catch(e){ alert('更新失败：' + ((e&&e.detail)||e)); }
    // 停止所有按钮的流光动画
    try { window.stopAllFx(); } catch(e) {}
  }

  /* ---------- CI 用户 ---------- */
  async function usersTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const d = await api('GET', '/api/users');
      usersCache = d.users || [];
      const rows = usersCache.map(u => `<tr>
        <td><b>${esc(u.name)}</b></td>
        <td class="mut">${esc(u.comment || '')}</td>
        <td class="mut" style="font-size:12px">${(u.dirs||[]).map(esc).join(', ') || '-'}</td>
        <td>
          <button class="ghost" onclick="${P}userSsh('${esc(u.name)}')">SSH 密钥</button>
          <button class="ghost danger" onclick="${P}userDelete('${esc(u.name)}')">删除</button>
        </td></tr>`).join('');
      view.innerHTML = navHtml() + `
      <div class="card"><h2>CI 用户</h2>
        <table><thead><tr><th>用户</th><th>说明</th><th>目录权限</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4" class="mut">暂无用户</td></tr>'}</tbody></table>
        <div class="row" style="margin-top:10px">
          <input id="newUserName" placeholder="用户名" style="width:120px">
          <button onclick="${P}userCreate()">创建用户</button>
        </div>
      </div>
      <div id="userSshBox"></div>`;
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }

  async function userCreate() {
    const name = document.getElementById('newUserName').value.trim();
    if (!name) return;
    try { await api('POST', '/api/users', { name }, true); await usersTab(); }
    catch(e){ alert('创建失败：' + ((e&&e.detail)||e)); }
  }

  async function userDelete(name) {
    if (!confirm('删除用户 ' + name + '？')) return;
    try { await api('DELETE', '/api/users/' + encodeURIComponent(name, true)); await usersTab(); }
    catch(e){ alert('删除失败：' + ((e&&e.detail)||e)); }
  }

  async function userSsh(name) {
    const box = document.getElementById('userSshBox');
    box.innerHTML = '<div class="card"><span class="spinner"></span></div>';
    try {
      const d = await api('GET', '/api/ssh/' + encodeURIComponent(name));
      const keys = (d.keys || []).map((k, i) => `<div class="row" style="margin:4px 0">
        <code style="font-size:11px;word-break:break-all">${esc(k.key || k)}</code>
        <button class="ghost danger" onclick="${P}sshRemove('${esc(name)}',${i})" style="margin-left:auto">删除</button>
      </div>`).join('');
      box.innerHTML = `<div class="card"><h2>SSH 密钥 · ${esc(name)}</h2>
        ${keys || '<div class="mut">暂无密钥</div>'}
        <div class="row" style="margin-top:8px">
          <textarea id="newSshKey" rows="2" style="width:100%;font-size:11px" placeholder="粘贴公钥"></textarea>
        </div>
        <button onclick="${P}sshAdd('${esc(name)}')" style="margin-top:6px">添加密钥</button>
      </div>`;
    } catch(e) { box.innerHTML = errCard(e); }
  }

  async function sshAdd(user) {
    const key = document.getElementById('newSshKey').value.trim();
    if (!key) return;
    try { await api('POST', '/api/ssh/' + encodeURIComponent(user, true), { key }); await userSsh(user); }
    catch(e){ alert('添加失败：' + ((e&&e.detail)||e)); }
  }

  async function sshRemove(user, index) {
    try { await api('DELETE', '/api/ssh/' + encodeURIComponent(user, true) + '/' + index); await userSsh(user); }
    catch(e){ alert('删除失败：' + ((e&&e.detail)||e)); }
  }

  /* ---------- 存储与版本 ---------- */
  let _storageApps = [];
  let _selectedApp = '';

  async function storageTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const d = await api('GET', '/api/storage/quota');
      _storageApps = d.apps || [];
      const quotaRows = _storageApps.map(a => {
        const pct = a.quota_mb > 0 ? Math.min(100, Math.round(a.usage_bytes / (a.quota_mb * 1024 * 1024) * 100)) : 0;
        return `<tr>
          <td>${esc(a.name)}</td>
          <td>${fmtSize(a.usage_bytes)}</td>
          <td>${a.quota_mb > 0 ? a.quota_mb + ' MB' : '不限'}</td>
          <td>${a.quota_mb > 0 ? `<div style="background:var(--line);height:6px;border-radius:3px;width:100px"><div style="background:${pct>90?'var(--err)':'var(--ok)'};height:100%;width:${pct}%;border-radius:3px"></div></div>` : ''}</td>
          <td><input type="number" value="${a.quota_mb||''}" placeholder="0" style="width:70px" id="q_${esc(a.name)}">
            <button class="ghost" onclick="${P}setQuota('${esc(a.name)}')">设置</button></td>
        </tr>`;
      }).join('');
      const appOpts = _storageApps.map(a => `<option value="${esc(a.name)}" ${a.name===_selectedApp?'selected':''}>${esc(a.name)}</option>`).join('');
      view.innerHTML = navHtml() + `
      <div class="card"><h2>存储配额</h2>
        <div class="row"><span class="mut">总用量: ${fmtSize(d.total_usage_bytes || 0)} / 总配额: ${d.total_quota_mb > 0 ? d.total_quota_mb + ' MB' : '不限'}</span></div>
        <table><thead><tr><th>应用</th><th>用量</th><th>配额</th><th>进度</th><th>设置</th></tr></thead>
        <tbody>${quotaRows}</tbody></table>
        <div class="row" style="margin-top:8px">
          <span class="mut">总配额(MB):</span>
          <input id="totalQuota" type="number" value="${d.total_quota_mb||''}" placeholder="0=不限" style="width:100px">
          <button class="ghost" onclick="${P}setTotalQuota()">设置总配额</button>
          <button class="ghost" onclick="${P}enforceQuota()">执行清理</button>
        </div>
      </div>
      <div class="card"><h2>版本管理</h2>
        <div class="row" style="margin-bottom:8px">
          <span class="mut">选择应用:</span>
          <select id="verAppSel" onchange="${P}loadVersions(this.value)" style="width:180px">
            <option value="">-- 选择应用 --</option>
            ${appOpts}
          </select>
        </div>
        <div id="verListBox"></div>
      </div>`;
      if (_selectedApp) loadVersions(_selectedApp);
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }

  async function loadVersions(name) {
    _selectedApp = name;
    const box = document.getElementById('verListBox');
    if (!name) { box.innerHTML = '<div class="mut">请选择应用查看版本</div>'; return; }
    box.innerHTML = '<div class="mut"><span class="spinner"></span> 加载版本...</div>';
    try {
      const [verData, appData] = await Promise.all([
        api('GET', '/api/apps/' + encodeURIComponent(name) + '/versions'),
        api('GET', '/api/apps/' + encodeURIComponent(name)),
      ]);
      const locked = new Set(appData.locked || []);
      const versions = verData.versions || [];
      const rows = versions.map(v => {
        const isLocked = locked.has(v.version);
        return `<tr>
          <td>${esc(v.version)}</td>
          <td class="mut">${fmtSize(v.size_bytes)}</td>
          <td class="mut" style="font-size:11px">${esc(v.rel)}</td>
          <td>${isLocked
            ? `<button class="ghost" onclick="${P}unlockVer('${esc(name)}','${esc(v.version)}')">解锁</button>
               <span class="ok" style="font-size:11px">已锁定</span>`
            : `<button class="ghost" onclick="${P}lockVer('${esc(name)}','${esc(v.version)}')">锁定</button>`}</td>
          <td><button class="ghost danger" onclick="${P}apkDelete('${esc(name)}','${esc(v.rel)}')">删除</button></td>
        </tr>`;
      }).join('');
      box.innerHTML = `
        <div class="mut" style="margin-bottom:6px">最新: ${verData.latest ? esc(verData.latest.version) : '-'} · 共 ${versions.length} 个版本</div>
        <table><thead><tr><th>版本</th><th>大小</th><th>文件</th><th>锁定</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="5" class="mut">暂无版本</td></tr>'}</tbody></table>`;
    } catch(e) { box.innerHTML = errCard(e); }
  }

  async function lockVer(name, version) {
    try { await api('POST', '/api/apps/' + encodeURIComponent(name, true) + '/versions/' + encodeURIComponent(version) + '/lock'); await loadVersions(name); }
    catch(e) { alert('锁定失败：' + ((e&&e.detail)||e)); }
  }

  async function unlockVer(name, version) {
    try { await api('POST', '/api/apps/' + encodeURIComponent(name, true) + '/versions/' + encodeURIComponent(version) + '/unlock'); await loadVersions(name); }
    catch(e) { alert('解锁失败：' + ((e&&e.detail)||e)); }
  }

  async function apkDelete(name, rel) {
    if (!confirm('删除文件 ' + rel + '？')) return;
    try { await api('POST', '/api/storage/delete', { paths: [rel] }, true); await loadVersions(name); }
    catch(e){ alert('删除失败：' + ((e&&e.detail)||e)); }
  }

  async function setQuota(name) {
    const mb = parseInt(document.getElementById('q_' + name).value) || 0;
    try { await api('POST', '/api/apps/' + encodeURIComponent(name, true) + '/quota', { mb }); await storageTab(); }
    catch(e){ alert('设置失败：' + ((e&&e.detail)||e)); }
  }

  async function setTotalQuota() {
    const mb = parseInt(document.getElementById('totalQuota').value) || 0;
    try { await api('POST', '/api/storage/quota', { total_mb: mb }, true); await storageTab(); }
    catch(e){ alert('设置失败：' + ((e&&e.detail)||e)); }
  }

  async function enforceQuota() {
    if (!confirm('执行配额清理？将删除最老的未锁定版本。')) return;
    try {
      const r = await api('POST', '/api/storage/enforce');
      const total = Object.values(r).reduce((s, arr) => s + arr.length, 0);
      alert('已清理 ' + total + ' 个文件');
      await storageTab();
    } catch(e){ alert('清理失败：' + ((e&&e.detail)||e)); }
  }

  return {
    title: '应用更新',
    sections: [
      { id: 'apps', title: '应用管理' },
      { id: 'users', title: 'CI 用户' },
      { id: 'storage', title: '存储与版本' },
    ],
    go: go,
    open: function (s) { go(s || 'apps'); },
    appsTab, addApp, saveApp, editApp, appDelete, appsCaddy, modalClose,
    toggleSslMode, toggleSslType, checkDomain, updateDefaultWorkdir,
    usersTab, userCreate, userDelete, userSsh, sshAdd, sshRemove,
    storageTab, loadVersions, lockVer, unlockVer, apkDelete,
    setQuota, setTotalQuota, enforceQuota,
  };
})();
