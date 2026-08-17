/* AUPS 插件：appupdate — 应用管理 / 部署配置 / CI 用户 / 存储与版本
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['appupdate'] = (function () {
  const P = 'AUPS_PLUGINS.appupdate.';
  let section = 'apps';
  let appsCache = [];

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

  /* ---------- 应用管理 ---------- */
  async function appsTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const d = await api('GET', '/api/apps');
      appsCache = d.apps || [];
      const rows = appsCache.map(a => {
        const dep = a.deploy || {};
        return `<tr>
          <td><b>${esc(a.name)}</b><div class="mut" style="font-size:11px">${esc(a.comment || '')}</div></td>
          <td class="mut" style="font-size:12px">${esc(dep.domain || '-')}</td>
          <td class="mut">${dep.port || '-'}</td>
          <td class="mut">${esc(dep.user || dep.ci_user || '-')}</td>
          <td class="mut" style="font-size:12px">${esc(a.dir)}</td>
          <td>
            <button class="ghost" onclick="${P}appDeploy('${esc(a.name)}')">部署</button>
            <button class="ghost danger" onclick="${P}appDelete('${esc(a.name)}')">删除</button>
          </td></tr>`;
      }).join('');
      view.innerHTML = navHtml() + `
      <div class="card"><h2>应用列表</h2>
        <table><thead><tr><th>应用</th><th>域名</th><th>端口</th><th>用户</th><th>目录</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="6" class="mut">暂无应用</td></tr>'}</tbody></table>
        <div class="row" style="margin-top:10px">
          <input id="newAppName" placeholder="应用名" style="width:150px">
          <button onclick="${P}appAdd()">注册应用</button>
          <button class="ghost" onclick="${P}appsCaddy()">同步反代路由</button>
        </div>
      </div>
      <div id="appDeployBox"></div>`;
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }

  async function appAdd() {
    const name = document.getElementById('newAppName').value.trim();
    if (!name) return;
    try { await api('POST', '/api/apps', { name }); await appsTab(); }
    catch(e){ alert('创建失败：' + ((e&&e.detail)||e)); }
  }

  async function appDelete(name) {
    if (!confirm('删除应用 ' + name + '？（仅取消注册，不删除文件）')) return;
    try { await api('DELETE', '/api/apps/' + encodeURIComponent(name)); await appsTab(); }
    catch(e){ alert('删除失败：' + ((e&&e.detail)||e)); }
  }

  async function appsCaddy() {
    try { await api('POST', '/api/apps/caddy', { reload: true }); alert('反代路由已更新'); }
    catch(e){ alert('更新失败：' + ((e&&e.detail)||e)); }
  }

  /* ---------- 部署配置 ---------- */
  async function appDeploy(name) {
    const box = document.getElementById('appDeployBox');
    box.innerHTML = '<div class="card"><span class="spinner"></span> 加载部署配置...</div>';
    try {
      const [app, domainR, sslR, portR, workdirR, userR, sshR] = await Promise.all([
        api('GET', '/api/apps/' + encodeURIComponent(name)),
        api('GET', '/api/apps/' + encodeURIComponent(name) + '/deploy/domain').catch(() => ({})),
        api('GET', '/api/apps/' + encodeURIComponent(name) + '/deploy/ssl').catch(() => ({})),
        api('GET', '/api/apps/' + encodeURIComponent(name) + '/deploy/port').catch(() => ({})),
        api('GET', '/api/apps/' + encodeURIComponent(name) + '/deploy/workdir').catch(() => ({})),
        api('GET', '/api/apps/' + encodeURIComponent(name) + '/deploy/user').catch(() => ({})),
        api('GET', '/api/apps/' + encodeURIComponent(name) + '/deploy/sshkey').catch(() => ({})),
      ]);
      const d = app.deploy || {};
      const ssl = d.ssl || {};
      box.innerHTML = `<div class="card"><h2>部署配置 · ${esc(name)}</h2>
        <div class="blk"><span class="mut">域名</span>
          <input id="dDomain" value="${esc(d.domain || '')}" placeholder="example.com"></div>
        <div class="blk"><span class="mut">SSL</span>
          <select id="dSslMode">
            <option value="none" ${ssl.mode==='none'?'selected':''}>无</option>
            <option value="auto" ${ssl.mode==='auto'?'selected':''}>自动申请</option>
            <option value="manual" ${ssl.mode==='manual'?'selected':''}>手动指定</option>
          </select></div>
        <div class="blk"><span class="mut">服务端口</span>
          <input id="dPort" type="number" value="${d.port || ''}" placeholder="8080"></div>
        <div class="blk"><span class="mut">工作目录</span>
          <input id="dWorkdir" value="${esc(d.workdir || '')}" placeholder="${esc(app.dir || '')}"></div>
        <div class="blk"><span class="mut">系统用户</span>
          <input id="dUser" value="${esc(d.user || '')}" placeholder="www-data">
          ${userR.ok ? '<span class="ok" style="font-size:11px">已存在</span>' : '<span class="bad" style="font-size:11px">未检测到</span>'}</div>
        <div class="blk"><span class="mut">CI 用户</span>
          <input id="dCiUser" value="${esc(d.ci_user || '')}" placeholder="updserver">
          ${sshR.ok ? '<span class="ok" style="font-size:11px">' + (sshR.keys||[]).length + ' 个密钥</span>' : ''}</div>
        <div class="row" style="margin-top:10px">
          <button onclick="${P}deploySave('${esc(name)}')">保存配置</button>
          <button class="ghost" onclick="${P}deployProxy('${esc(name)}')">应用到反代</button>
        </div>
        <div class="mut" style="margin-top:8px">配置保存后需「应用到反代」才会生效（写入 Caddyfile/nginx.conf 并 reload）。</div>
      </div>`;
    } catch(e) { box.innerHTML = errCard(e); }
  }

  async function deploySave(name) {
    const body = {
      domain: document.getElementById('dDomain').value.trim(),
      ssl: { mode: document.getElementById('dSslMode').value },
      port: parseInt(document.getElementById('dPort').value) || 0,
      workdir: document.getElementById('dWorkdir').value.trim(),
      user: document.getElementById('dUser').value.trim(),
      ci_user: document.getElementById('dCiUser').value.trim(),
    };
    try {
      await api('POST', '/api/apps/' + encodeURIComponent(name) + '/deploy', body);
      alert('部署配置已保存');
      await appDeploy(name);
    } catch(e) { alert('保存失败：' + ((e&&e.detail)||e)); }
  }

  async function deployProxy(name) {
    try {
      await api('POST', '/api/apps/caddy', { reload: true });
      alert('已应用到反代');
    } catch(e) { alert('应用失败：' + ((e&&e.detail)||e)); }
  }

  /* ---------- CI 用户 ---------- */
  async function usersTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const d = await api('GET', '/api/users');
      const users = d.users || [];
      const rows = users.map(u => `<tr>
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
    try { await api('POST', '/api/users', { name }); await usersTab(); }
    catch(e){ alert('创建失败：' + ((e&&e.detail)||e)); }
  }

  async function userDelete(name) {
    if (!confirm('删除用户 ' + name + '？')) return;
    try { await api('DELETE', '/api/users/' + encodeURIComponent(name)); await usersTab(); }
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
    try { await api('POST', '/api/ssh/' + encodeURIComponent(user), { key }); await userSsh(user); }
    catch(e){ alert('添加失败：' + ((e&&e.detail)||e)); }
  }

  async function sshRemove(user, index) {
    try { await api('DELETE', '/api/ssh/' + encodeURIComponent(user) + '/' + index); await userSsh(user); }
    catch(e){ alert('删除失败：' + ((e&&e.detail)||e)); }
  }

  /* ---------- 存储与版本 ---------- */
  let _storageApps = [];
  let _storageVersions = {};
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

      // 版本选择器
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

      // 自动加载上次选择的应用
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
               <span class="ok" style="font-size:11px">🔒 已锁定</span>`
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
    try {
      await api('POST', '/api/apps/' + encodeURIComponent(name) + '/versions/' + encodeURIComponent(version) + '/lock');
      await loadVersions(name);
    } catch(e) { alert('锁定失败：' + ((e&&e.detail)||e)); }
  }

  async function unlockVer(name, version) {
    try {
      await api('POST', '/api/apps/' + encodeURIComponent(name) + '/versions/' + encodeURIComponent(version) + '/unlock');
      await loadVersions(name);
    } catch(e) { alert('解锁失败：' + ((e&&e.detail)||e)); }
  }

  async function apkDelete(name, rel) {
    if (!confirm('删除文件 ' + rel + '？')) return;
    try { await api('POST', '/api/storage/delete', { paths: [rel] }); await loadVersions(name); }
    catch(e){ alert('删除失败：' + ((e&&e.detail)||e)); }
  }

  async function setQuota(name) {
    const mb = parseInt(document.getElementById('q_' + name).value) || 0;
    try { await api('POST', '/api/apps/' + encodeURIComponent(name) + '/quota', { mb }); await storageTab(); }
    catch(e){ alert('设置失败：' + ((e&&e.detail)||e)); }
  }

  async function setTotalQuota() {
    const mb = parseInt(document.getElementById('totalQuota').value) || 0;
    try { await api('POST', '/api/storage/quota', { total_mb: mb }); await storageTab(); }
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
    appsTab, appAdd, appDelete, appsCaddy,
    appDeploy, deploySave, deployProxy,
    usersTab, userCreate, userDelete, userSsh, sshAdd, sshRemove,
    storageTab, loadVersions, lockVer, unlockVer, apkDelete,
    setQuota, setTotalQuota, enforceQuota,
  };
})();
