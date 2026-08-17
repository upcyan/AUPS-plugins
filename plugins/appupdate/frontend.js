/* AUPS 插件：appupdate — 应用管理 / 部署配置 / CI 用户 / 存储与版本
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['appupdate'] = (function () {
  const P = 'AUPS_PLUGINS.appupdate.';
  let section = 'apps';
  let appsCache = [];
  let usersCache = [];

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
        <div class="card" style="min-width:480px;max-width:90vw;max-height:85vh;overflow:auto">${html}</div>
      </div>`;
  }
  function modalClose() { const m = document.getElementById('appModal'); if (m) m.innerHTML = ''; }

  /* ---------- 应用管理 ---------- */
  async function appsTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const [d, ud] = await Promise.all([
        api('GET', '/api/apps'),
        api('GET', '/api/users').catch(() => ({users:[]})),
      ]);
      appsCache = d.apps || [];
      usersCache = ud.users || [];
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
          <input id="newAppName" placeholder="应用名" style="width:150px">
          <button onclick="${P}appAdd()">注册应用</button>
          <button class="ghost" onclick="${P}appsCaddy()">同步反代路由</button>
        </div>
      </div>
      <div id="appModal"></div>`;
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

  /* ---------- 编辑应用部署配置（弹窗） ---------- */
  async function editApp(name) {
    try {
      const app = await api('GET', '/api/apps/' + encodeURIComponent(name));
      const d = app.deploy || {};
      const ssl = d.ssl || {};
      // CI 用户下拉选项
      const userOpts = usersCache.map(u =>
        `<option value="${esc(u.name)}" ${d.ci_user===u.name?'selected':''}>${esc(u.name)}${u.comment ? ' ('+esc(u.comment)+')' : ''}</option>`
      ).join('');
      modal(`
        <h2>编辑部署配置 · ${esc(name)}</h2>
        <div class="blk"><span class="mut">域名</span>
          <input id="eDomain" value="${esc(d.domain || '')}" placeholder="example.com"></div>
        <div class="blk"><span class="mut">SSL</span>
          <select id="eSslMode">
            <option value="none" ${ssl.mode==='none'?'selected':''}>无</option>
            <option value="auto" ${ssl.mode==='auto'?'selected':''}>自动申请</option>
            <option value="manual" ${ssl.mode==='manual'?'selected':''}>手动指定</option>
          </select></div>
        <div class="blk"><span class="mut">服务端口</span>
          <input id="ePort" type="number" value="${d.port || ''}" placeholder="8080"></div>
        <div class="blk"><span class="mut">工作目录</span>
          <input id="eWorkdir" value="${esc(d.workdir || '')}" placeholder="${esc(app.dir || '')}"></div>
        <div class="blk"><span class="mut">CI 用户</span>
          <select id="eCiUser">
            <option value="">-- 不指定 --</option>
            ${userOpts}
          </select>
          <div class="mut" style="font-size:11px;margin-top:4px">选择后将自动授予该用户对工作目录的读写权限</div>
        </div>
        <div class="row" style="margin-top:12px">
          <button onclick="${P}saveDeploy('${esc(name)}')">保存并授权</button>
          <button class="ghost" onclick="${P}modalClose()">取消</button>
        </div>
      `);
    } catch(e) { alert('加载失败：' + ((e&&e.detail)||e)); }
  }

  async function saveDeploy(name) {
    const ciUser = document.getElementById('eCiUser').value;
    const workdir = document.getElementById('eWorkdir').value.trim() || undefined;
    const body = {
      domain: document.getElementById('eDomain').value.trim(),
      ssl: { mode: document.getElementById('eSslMode').value },
      port: parseInt(document.getElementById('ePort').value) || 0,
      workdir: workdir,
      ci_user: ciUser,
    };
    try {
      await api('POST', '/api/apps/' + encodeURIComponent(name) + '/deploy', body);
      // 自动授予 CI 用户目录权限
      if (ciUser && workdir) {
        try {
          await api('POST', '/api/users/' + encodeURIComponent(ciUser) + '/dirs', { path: workdir });
        } catch(e) {
          // 权限授予失败不阻断，仅提示
          alert('部署配置已保存，但目录授权失败：' + ((e && e.message) || e) + '\n请在「CI 用户」页手动授权。');
          modalClose();
          await appsTab();
          return;
        }
      } else if (ciUser && !workdir) {
        // 有用户但无工作目录，提示
        alert('已保存。如需授权目录访问，请指定工作目录后重新保存。');
      }
      alert('部署配置已保存' + (ciUser ? '，目录权限已授予 ' + ciUser : ''));
      modalClose();
      await appsTab();
    } catch(e) { alert('保存失败：' + ((e&&e.detail)||e)); }
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
    try { await api('POST', '/api/apps/' + encodeURIComponent(name) + '/versions/' + encodeURIComponent(version) + '/lock'); await loadVersions(name); }
    catch(e) { alert('锁定失败：' + ((e&&e.detail)||e)); }
  }

  async function unlockVer(name, version) {
    try { await api('POST', '/api/apps/' + encodeURIComponent(name) + '/versions/' + encodeURIComponent(version) + '/unlock'); await loadVersions(name); }
    catch(e) { alert('解锁失败：' + ((e&&e.detail)||e)); }
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
    editApp, saveDeploy, modalClose,
    usersTab, userCreate, userDelete, userSsh, sshAdd, sshRemove,
    storageTab, loadVersions, lockVer, unlockVer, apkDelete,
    setQuota, setTotalQuota, enforceQuota,
  };
})();
