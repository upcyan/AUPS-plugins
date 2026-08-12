/* AUPS 插件：appupdate —— 应用管理 / CI 用户 / SSH
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / headers / alert / confirm。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['appupdate'] = (function () {
  const P = 'AUPS_PLUGINS.appupdate.';
  let section = 'apps';
  let discoverList = [];
  let storageTotalQuota = 0;

  function navHtml() {
    return `<div class="secnav">
      <button class="${section === 'apps' ? 'on' : ''}" onclick="${P}go('apps')">应用管理</button>
      <button class="${section === 'users' ? 'on' : ''}" onclick="${P}go('users')">CI 用户</button>
      <button class="${section === 'ssh' ? 'on' : ''}" onclick="${P}go('ssh')">SSH 公钥</button>
    </div>`;
  }

  /* ---------- 应用管理（含存储管理） ---------- */
  async function appsTab() {
    const [d, q, a, disc] = await Promise.all([
      api('GET', '/api/apps'),
      api('GET', '/api/storage/quota'),
      api('GET', '/api/storage/apks'),
      api('GET', '/api/apps/discover')
    ]);
    discoverList = disc.candidates || [];
    const tq = q.total_quota_mb || 0;
    storageTotalQuota = tq;
    const totalOver = tq && q.total_mb > tq;
    let rows = '';
    for (const app of d.apps) {
      let latest = '<span class="mut">-</span>', count = '-', err = '';
      try {
        const v = await api('GET', `/api/apps/${app.name}/versions`, null, true);
        latest = v.latest ? v.latest.version : '<span class="mut">-</span>';
        count = v.versions.length;
      } catch (e) { err = '<span class="bad">读取失败</span>'; }
      rows += `<tr><td>${esc(app.name)}</td><td class="mut">${esc(app.comment || '')}</td><td>${esc(app.dir)}</td>
        <td>${latest}</td><td>${count}</td><td class="mut">${err}</td>
        <td><div class="row"><button class="ghost" onclick="${P}appVersions('${app.name}')">版本</button>
        <button class="danger" onclick="${P}delApp('${app.name}')">删除</button></div></td></tr>`;
    }
    const appRows = q.apps.map(x => {
      const pct = x.quota_mb ? Math.min(100, Math.round(x.size_mb / x.quota_mb * 100)) : 0;
      return `<tr>
        <td>${esc(x.name)}</td>
        <td>${fmt(x.size_bytes)}</td>
        <td>${x.quota_mb ? x.quota_mb + ' MB' : '<span class="mut">不限</span>'}</td>
        <td>${x.quota_mb ? `<div class="row"><div style="flex:1;height:8px;background:var(--input);border-radius:4px;min-width:60px"><div style="height:100%;width:${pct}%;background:${x.over ? 'var(--bad)' : 'var(--ok)'};border-radius:4px"></div></div><span class="mut">${pct}%</span></div>` : '<span class="mut">未设限制</span>'}</td>
        <td>${x.over ? '<span class="bad">超出配额</span>' : '<span class="ok">正常</span>'}</td>
        <td><div class="row">
          <input type="text" placeholder="MB，0=不限" style="min-width:70px">
          <button class="ghost" onclick="${P}appQuotaBtn('${esc(x.name)}',this)">设置</button>
        </div></td></tr>`;
    }).join('') || '<tr><td colspan="6" class="mut">尚未注册应用</td></tr>';
    const cand = discoverList.map((c, i) => `<div class="row" style="margin:6px 0">
      <span>${esc(c.name)}</span><span class="mut">${esc(c.dir)}（${c.apk_count} 个 APK）</span>
      <button class="ghost" onclick="${P}storageReg(${i})">注册</button></div>`).join('');
    view.innerHTML = navHtml() + `
    <div class="card"><h2>已注册应用</h2>
      <div class="row" style="margin-bottom:10px">
        <input id="appName" type="text" placeholder="名称（如 dateforshift）">
        <input id="appDir" type="text" placeholder="目录（默认 /var/www/html/名称，可选）" style="min-width:320px">
        <button onclick="${P}addApp()">注册</button>
        <button class="ghost" onclick="${P}syncCaddy()" title="按已注册应用重写 Caddyfile 下载路由并 reload">同步 Caddy</button>
      </div>
      <table><tr><th>名称</th><th>备注</th><th>目录</th><th>最新版</th><th>版本数</th><th></th><th></th></tr>
      ${d.apps.length ? rows : '<tr><td colspan="7" class="mut">尚未注册应用</td></tr>'}
      </table></div>
    <div class="card" id="appVersionsCard" class="hide"><h2 id="appVersionsTitle">版本</h2>
      <table><tr><th>版本号</th><th>相对路径</th><th>大小</th><th></th></tr>
      <tbody id="appVersionsBody"></tbody></table></div>
    <div class="card"><h2>总存储 · ${esc(q.base)}</h2>
      <div class="row">
        <span>已用 <b>${fmt(q.total_bytes)}</b>${tq ? '<span class="mut"> / 上限 ' + tq + ' MB</span>' : ''}</span>
        ${totalOver ? '<span class="bad">已超出总配额，请清理或调整</span>' : ''}
      </div>
      <div class="row" style="margin-top:8px">
        <input id="totalQuota" type="text" placeholder="总配额 MB（0=不限）" value="${tq || ''}" style="min-width:150px">
        <button onclick="${P}setTotalQuota()">设置总配额</button>
        <button class="ghost" onclick="${P}enforceQuota()">按配额清理</button>
      </div>
      <div class="mut" style="margin-top:6px">总配额不能小于任一应用配额；「按配额清理」会删除超出限制的最老未锁定版本。</div></div>
    <div class="card"><h2>应用配额</h2>
      <table><tr><th>应用</th><th>已用</th><th>配额</th><th>占用比</th><th>状态</th><th></th></tr>
      ${appRows}</table></div>
    <div class="card"><h2>APK 文件</h2><table>
      <tr><th>应用</th><th>版本</th><th>文件</th><th>锁定</th><th>大小</th><th></th></tr>
      ${a.apks.map(x => {
        const lockBtn = (x.app && x.version)
          ? (x.locked
              ? `<button class="ghost" onclick="${P}toggleLock('${esc(x.app)}','${esc(x.version)}',false,this)">解锁</button>`
              : `<button class="ghost" onclick="${P}toggleLock('${esc(x.app)}','${esc(x.version)}',true,this)">锁定</button>`)
          : '';
        return `<tr><td>${x.app ? esc(x.app) : '<span class="bad">未注册</span>'}</td><td>${esc(x.version) || '<span class="mut">-</span>'}</td><td>${x.path}</td><td>${x.locked ? '<span class="ok">已锁定</span>' : ''}</td><td>${fmt(x.size_bytes)}</td>
          <td><div class="row">${lockBtn}<button class="ghost" onclick="${P}delApk('${x.path}', this)">删除</button></div></td></tr>`;
      }).join('')}
    </table>
    <div class="mut" style="margin-top:6px">「锁定」的版本在配额清理时不会被删除。</div></div>
    <div class="card"><h2>未注册应用检测</h2>
      ${cand || '<div class="mut">站点目录下未发现含 APK 的未注册应用</div>'}
      <div class="mut" style="margin-top:6px">自动扫描站点目录；检测到含 APK 但未注册的应用目录可一键注册，注册后可设配额并生成下载路由。</div></div>`;
  }
  async function appVersions(name) {
    const v = await api('GET', `/api/apps/${name}/versions`);
    document.getElementById('appVersionsCard').classList.remove('hide');
    document.getElementById('appVersionsTitle').textContent = '版本 · ' + name + (v.latest ? '（最新 ' + v.latest.version + '）' : '');
    document.getElementById('appVersionsBody').innerHTML = v.versions.map(x => `
      <tr><td>${x.version}</td><td>${x.rel}</td><td>${fmt(x.size_bytes)}</td>
      <td><button class="danger" onclick="${P}delAppApk('${name}','${x.file}')">删除</button></td></tr>`).join('')
      || '<tr><td colspan="4" class="mut">无带版本号的 APK</td></tr>';
  }
  async function delAppApk(name, file) {
    if (!confirm('删除 ' + file + ' ？')) return;
    await api('POST', '/api/storage/delete', { paths: [file] });
    await appVersions(name);
  }
  async function addApp() {
    const name = document.getElementById('appName').value.trim();
    if (!name) { alert('请输入应用名称'); return; }
    const dir = document.getElementById('appDir').value.trim();
    await api('POST', '/api/apps', { name, dir });
    await appsTab();
  }
  async function delApp(name) {
    if (!confirm('取消注册应用 ' + name + '？（目录与 APK 文件不会被删除）')) return;
    await api('DELETE', `/api/apps/${name}`);
    await appsTab();
  }
  async function syncCaddy() {
    await api('POST', '/api/apps/caddy');
    alert('Caddyfile 已更新并 reload');
  }
  async function setTotalQuota() {
    const v = parseInt(document.getElementById('totalQuota').value);
    if (isNaN(v)) { alert('请输入数字'); return; }
    await api('POST', '/api/storage/quota', { total_mb: v });
    await appsTab();
  }
  async function appQuotaBtn(name, btn) {
    const inp = btn.parentElement.querySelector('input');
    const v = parseInt(inp.value);
    if (isNaN(v)) { alert('请输入数字（0=不限）'); return; }
    if (storageTotalQuota && v > storageTotalQuota) { alert('该应用配额 ' + v + ' MB 超过总配额 ' + storageTotalQuota + ' MB'); return; }
    await api('POST', `/api/apps/${name}/quota`, { mb: v });
    await appsTab();
  }
  async function toggleLock(app, version, lock, el) {
    el.disabled = true;
    await api('POST', `/api/apps/${app}/versions/${version}/${lock ? 'lock' : 'unlock'}`);
    await appsTab();
  }
  async function enforceQuota() {
    if (!confirm('按配额清理：删除超出配额（应用/总配额）的最老未锁定版本，确认执行？')) return;
    const r = await api('POST', '/api/storage/enforce');
    let n = 0; for (const k in r) n += (r[k] || []).length;
    alert('清理完成，共删除 ' + n + ' 个文件');
    await appsTab();
  }
  async function storageReg(i) {
    const c = discoverList[i];
    await api('POST', '/api/apps', { name: c.name, dir: c.dir });
    await appsTab();
  }
  async function delApk(path, el) {
    if (!confirm('删除 ' + path + ' ？')) return;
    el.disabled = true;
    await api('POST', '/api/storage/delete', { paths: [path] });
    await appsTab();
  }

  function go(s) {
    section = s || 'apps';
    if (section === 'users') usersTab();
    else if (section === 'ssh') sshTab(null);
    else appsTab();
  }

  /* ---------- CI 用户 ---------- */
  async function usersTab() {
    const d = await api('GET', '/api/users');
    const rows = (d.users || []).map(x => `<tr>
      <td>${esc(x.name)}</td><td class="mut">${esc(x.comment || '')}</td>
      <td>${(x.dirs || []).join('<br>') || '<span class="mut">(无)</span>'}</td>
      <td><div class="row">
        <input type="text" placeholder="/var/www/html/xxx" onchange="${P}grantDir('${x.name}',this.value)">
        <button class="ghost" onclick="${P}openSSH('${x.name}')">SSH 密钥</button>
        <button class="danger" onclick="${P}delUser('${x.name}')">删除</button>
      </div></td></tr>`).join('');
    view.innerHTML = navHtml() + `
      <div class="card"><h2>CI 用户（APK 上传账号）</h2>
        <div class="row" style="margin-bottom:10px">
          <input id="uname" type="text" placeholder="用户名（默认 updserver）">
          <input id="ukey" type="text" placeholder="公钥（可选）" style="min-width:360px">
          <button onclick="${P}createUser()">创建</button>
        </div>
        <table><tr><th>用户</th><th>备注</th><th>可读写目录</th><th></th></tr>
        ${rows || '<tr><td colspan="4" class="mut">暂无用户</td></tr>'}
        </table></div>`;
  }
  async function createUser() {
    const name = document.getElementById('uname').value.trim() || 'updserver';
    const key = document.getElementById('ukey').value.trim();
    await api('POST', '/api/users', {name: name, key: key});
    await usersTab();
  }
  async function grantDir(name, path) {
    await api('POST', `/api/users/${name}/dirs`, {path: path});
    await usersTab();
  }
  async function delUser(name) {
    if (!confirm('删除用户 ' + name + '（含其主目录与所有 ACL 授权）？')) return;
    await api('DELETE', `/api/users/${name}`);
    await usersTab();
  }
  async function openSSH(user) { await sshTab(user); }

  /* ---------- SSH 公钥 ---------- */
  async function sshTab(user) {
    user = user || (prompt('输入用户名') || '');
    if (!user) return;
    const d = await api('GET', `/api/ssh/${user}`);
    view.innerHTML = navHtml() + `
      <div class="card"><h2>SSH 公钥 · ${user}</h2>
        <div class="row" style="margin-bottom:10px">
          <input id="skey" type="text" placeholder="粘贴公钥 ssh-... " style="min-width:400px">
          <button onclick="${P}addKey('${user}')">添加</button>
        </div>
        <table><tr><th>#</th><th>类型</th><th>备注</th><th></th></tr>
        ${(d.keys || []).map(x => `<tr><td>${x.index}</td><td>${x.type}</td><td class="mut">${x.comment}</td>
          <td><button class="danger" onclick="${P}delKey('${user}',${x.index})">删除</button></td></tr>`).join('')}
        </table></div>`;
  }
  async function addKey(user) {
    const key = document.getElementById('skey').value.trim();
    await api('POST', `/api/ssh/${user}`, {key: key});
    await sshTab(user);
  }
  async function delKey(user, index) {
    if (!confirm('删除公钥 #' + index + ' ？')) return;
    await api('DELETE', `/api/ssh/${user}/${index}`);
    await sshTab(user);
  }

  return {
    title: '应用更新',
    sections: [
      {id: 'apps', title: '应用管理'}, {id: 'users', title: 'CI 用户'}, {id: 'ssh', title: 'SSH 公钥'}
    ],
    go: go,
    open: function (s) { go(s || 'apps'); },
    appsTab: appsTab, appVersions: appVersions, delAppApk: delAppApk,
    addApp: addApp, delApp: delApp, syncCaddy: syncCaddy, setTotalQuota: setTotalQuota,
    appQuotaBtn: appQuotaBtn, toggleLock: toggleLock, enforceQuota: enforceQuota,
    storageReg: storageReg, delApk: delApk,
    usersTab: usersTab, createUser: createUser, grantDir: grantDir, delUser: delUser,
    openSSH: openSSH, sshTab: sshTab, addKey: addKey, delKey: delKey
  };
})();

/* 插件向总览注册卡片：下载统计、应用概览（一个插件可注册多张） */
window.AUPS_CARDS = window.AUPS_CARDS || {};
window.AUPS_CARDS['downloads'] = {
  title: '下载统计',
  source: 'appupdate',
  w: 2, h: 1, minW: 1, maxW: 3, minH: 1, maxH: 2,
  refresh: 60,
  render: async function (el) {
    el.innerHTML = '<span class="mut">加载中...</span>';
    const d = await api('GET', '/api/stats/downloads', null, true).catch(e => ({e: (e && e.message) || '失败'}));
    if (d.e) { el.innerHTML = '<span class="bad">加载失败: ' + esc(d.e) + '</span>'; return; }
    el.innerHTML = `<div class="mut" style="margin-bottom:6px">日志: ${esc(d.source || '-')}</div>
      <table><tr><th>应用</th><th>下载</th><th>独立IP</th></tr>
      ${(d.apps || []).map(x => `<tr><td>${esc(x.name)}</td><td>${x.total}</td><td>${x.unique_ips}</td></tr>`).join('')
        || '<tr><td colspan="3" class="mut">暂无下载记录</td></tr>'}
      </table>
      <button class="ghost" style="margin-top:8px" onclick="enableAccessLog()">开启access日志</button>`;
  }
};
window.AUPS_CARDS['appsoverview'] = {
  title: '应用概览',
  source: 'appupdate',
  w: 1, h: 1, minW: 1, maxW: 3, minH: 1, maxH: 2,
  render: async function (el) {
    el.innerHTML = '<span class="mut">加载中...</span>';
    const d = await api('GET', '/api/apps', null, true).catch(e => ({e: (e && e.message) || '失败'}));
    if (d.e) { el.innerHTML = '<span class="bad">加载失败: ' + esc(d.e) + '</span>'; return; }
    const apps = d.apps || [];
    el.innerHTML = `<div class="mut" style="margin-bottom:6px">已注册 ${apps.length} 个应用</div>
      <table><tr><th>应用</th><th>最新版</th></tr>
      ${apps.slice(0, 8).map(x => `<tr><td>${esc(x.name)}</td><td class="mut">-</td></tr>`).join('')
        || '<tr><td colspan="2" class="mut">暂无应用</td></tr>'}
      </table>`;
  }
};
