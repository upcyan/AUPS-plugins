/* AUPS 插件：caddy — Caddyfile 管理 / 实例控制 / SSL 接入
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 * v1.5.0：新增 SSL 标签页，支持 Flexible / DNS-01 两种 Cloudflare 接入方案。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['caddy'] = (function () {
  const P = 'AUPS_PLUGINS.caddy.';
let section = 'caddyfile';
let currentDeploy = 'host';

function navHtml() {
  return `<div class="secnav">
    <button class="${section === 'caddyfile' ? 'on' : ''}" onclick="${P}go('caddyfile')">Caddyfile 管理</button>
    <button class="${section === 'instance' ? 'on' : ''}" onclick="${P}go('instance')">实例控制</button>
    <button class="${section === 'ssl' ? 'on' : ''}" onclick="${P}go('ssl')">SSL 接入</button>
  </div>`;
}

  function errCard(e) {
    const msg = (e && e.message) || e || '未知错误';
    return `<div class="card"><h2>加载失败</h2>
      <pre style="white-space:pre-wrap">${esc(msg)}</pre>
      <div class="mut" style="margin-top:6px">请确认面板服务已重启、插件已启用（插件中心）。</div></div>`;
  }

  function go(s) {
    section = s || 'caddyfile';
    if (section === 'caddyfile') caddyfileTab();
    else if (section === 'instance') instanceTab();
    else if (section === 'ssl') sslTab();
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
        <div class="row"><span class="mut">配置: ${esc(cf.path)} · 部署: ${deploy}${st.version ? ' · Caddy ' + esc(st.version) : ''}</span></div>
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
  async function caddyfileReload() {
    // 通过面板 api() 函数调用（自动携带会话 token）
    try {
      const r = await api('POST', '/api/caddy/instance/reload', {}, true);
      alert('已重载 Caddy');
    } catch(e) {
      alert('重载失败：' + ((e && e.detail) || e));
    }
    await caddyfileTab();
  }
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
      const cached = sitesCache.find(s => s.host === host);
      if (cached) { cached.mode = mode; cached.target = target; }
      siteClose();
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
  let _instTimer = null;
  async function instanceTab() {
    if (_instTimer) { clearInterval(_instTimer); _instTimer = null; }
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const [cs, pt] = await Promise.all([
        api('GET', '/api/caddy/status'),
        api('GET', '/api/ports')
      ]);
      const listening = (pt.listening || []).map(x => `${x.local}  (${x.process})`).join('\n');
      const c = cs.container || {};
      currentDeploy = cs.deploy || 'host';
      const deployHtml = cs.deploy === 'container'
        ? `容器 <b>${esc(c.name||'-')}</b> · ${esc(c.runtime||'-')} · ${esc(c.image||'-')} · ${c.exists ? (c.running ? '<b style="color:var(--ok)">运行中</b>' : '<b style="color:var(--bad)">已停止</b>') : '<span class="mut">未创建</span>'}`
        : `实机 · ${cs.version ? 'Caddy ' + esc(cs.version) : '未安装'}`;
      const installBtn = !cs.installed
        ? `<div class="row" style="margin-top:12px;padding:10px;border:1px solid var(--bad);border-radius:6px">
             <span style="color:var(--bad)">${cs.deploy === 'container' ? (c.supported ? 'Caddy 容器尚未创建' : '未检测到 Docker/Podman') : 'Caddy 未安装'}</span>
             <button onclick="${P}caddyInstall()" style="margin-left:auto">${cs.deploy === 'container' ? '部署 Caddy 容器' : '安装 Caddy'}</button>
           </div>`
        : '';
      view.innerHTML = navHtml() + `
      <div class="card"><h2>实例状态</h2>
        <div class="row"><span class="mut">部署: ${deployHtml}</span></div>
        ${installBtn}
        <div class="row" style="margin-top:12px">
          <button onclick="${P}inst('start')">启动</button>
          <button onclick="${P}inst('stop')">停止</button>
          <button onclick="${P}inst('restart')">重启</button>
          <button onclick="${P}inst('reload')">重载</button>
          <button class="ghost" onclick="${P}instanceTab()" style="margin-left:auto">刷新状态</button>
        </div>
      </div>
      <div class="card"><h2>监听端口</h2><pre>${listening || '无'}</pre></div>
      <div class="card"><h2>工作日志</h2>
        <div class="row"><button class="ghost" onclick="${P}caddyLogs()">加载最近日志</button>
        <span class="mut" style="font-size:12px;margin-left:8px">最近 100 行</span></div>
        <pre id="ccLogBox" style="margin-top:8px;max-height:400px;overflow:auto;color:var(--mut);font-size:12px">点击「加载最近日志」查看</pre>
      </div>`;
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }
  async function caddyLogs() {
    const box = document.getElementById('ccLogBox');
    if (!box) return;
    box.textContent = '加载中...';
    try {
      const d = await api('GET', '/api/caddy/journal?lines=100');
      if (d.error) { box.textContent = d.error; return; }
      box.textContent = (d.lines || []).join('\n') || '(无日志)';
    } catch (e) { box.textContent = '加载失败: ' + ((e && e.message) || e); }
  }
  async function caddyInstall() {
    const message = currentDeploy === 'container'
      ? '部署 Caddy 容器？将拉取官方镜像，并使用 host 网络接入宿主机应用端口。'
      : '安装 Caddy？将通过系统包管理器安装并部署到面板目录。';
    if (!confirm(message)) return;
    try {
      const r = await api('POST', '/api/caddy/install');
      alert('Caddy 已安装: ' + (r.message || ''));
      await instanceTab();
    } catch (e) { alert('安装失败: ' + ((e && e.detail) || e)); }
  }
  async function inst(action) {
    const names = { start:'启动', stop:'停止', restart:'重启', reload:'重载' };
    if (action === 'stop' && !confirm('确定停止 Caddy 服务？')) return;
    try { const r = await api('POST', '/api/caddy/instance/' + action); alert('已' + (names[action]||action) + (r.deploy === 'container' ? '（容器）' : '')); await instanceTab(); }
    catch(e){ alert((names[action]||action) + '失败：' + ((e&&e.detail)||e)); }
  }

  /* ---------- SSL 接入方案 ---------- */
  async function sslTab() {
    view.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const st = await api('GET', '/api/caddy/ssl/status');
      const mode = st.configured_mode || 'none';
      const hint = st.caddyfile_hint || '未检测到特殊配置';
      const hasDns = st.binary_supports_dns01;
      const httpSites = st.http_sites_count;

      const modeBadge = mode === 'flexible' ? '<span style="color:var(--ok)">Flexible (HTTP 80)</span>'
        : mode === 'dns01' ? '<span style="color:var(--accent)">DNS-01 (Full Strict)</span>'
        : '<span class="mut">默认自动 HTTPS</span>';

      const dnsStatus = hasDns ? '<span style="color:var(--ok)">✓ 支持</span>' : '<span style="color:var(--bad)">✗ 不支持（需自定义构建）</span>';

      view.innerHTML = navHtml() + `
      <div class="card"><h2>SSL 接入方案（Cloudflare 场景）</h2>
        <div class="blk"><span class="mut">当前方案</span><strong>${modeBadge}</strong></div>
        <div class="blk"><span class="mut">配置提示</span><span class="mut">${esc(hint)}</span></div>
        <div class="blk"><span class="mut">DNS-01 插件</span>${dnsStatus}</div>
        <div class="blk"><span class="mut">HTTP 孪生站点</span><span class="mut">${httpSites} 个</span></div>
      </div>

      <div class="card"><h2>方案 A：Flexible（推荐快速接入）</h2>
        <div class="mut" style="margin-bottom:8px">
          适用场景：不想折腾 caddy 编译、域名已走 Cloudflare 代理、可接受源站仅 HTTP。<br>
          原理：Cloudflare 边缘终结 TLS（Flexible），回源走 HTTP(80)；caddy 仅监听 80 端口服务内容，<br>
          全局 <code>auto_https disable_redirects</code> 防重定向循环，为每个站点自动生成 <code>http://</code> 孪生块。
        </div>
        <div class="row" style="margin-top:8px">
          <input id="sslFlexEmail" type="email" placeholder="ACME 邮箱（可选）" value="${esc(st.email || '')}" style="flex:1">
        </div>
        <div class="row" style="margin-top:8px">
          <button onclick="${P}sslApplyFlexible()">启用 Flexible</button>
        </div>
        <details style="margin-top:10px"><summary class="mut">操作步骤（点击展开）</summary>
          <ol class="mut" style="margin-top:6px;line-height:1.8">
            <li>Cloudflare 面板 → SSL/TLS → Overview → 设为 <b>Flexible</b></li>
            <li>点击上方「启用 Flexible」，面板自动：<br>
              &nbsp;&nbsp;① 写入全局 <code>auto_https disable_redirects</code><br>
              &nbsp;&nbsp;② 为现有站点生成 <code>http://domain { ... }</code> 孪生块<br>
              &nbsp;&nbsp;③ reload caddy</li>
            <li>验证：<code>curl -sk https://your.domain/</code> 应返回内容（走 Cloudflare Flexible 回源 80）</li>
            <li>如需恢复默认：点击下方「恢复默认」并将 Cloudflare 改回 <b>Full (strict)</b></li>
          </ol>
        </details>
      </div>

      <div class="card"><h2>方案 B：DNS-01（标准 Full Strict，需自定义 caddy）</h2>
        <div class="mut" style="margin-bottom:8px">
          适用场景：需要源站真实证书、Cloudflare 保持 <b>Full (strict)</b>、<br>
          愿意替换 caddy 二进制为带 <code>github.com/caddy-dns/cloudflare</code> 插件的版本。<br>
          原理：caddy 通过 Cloudflare API 创建 TXT 记录完成 DNS-01 挑战，自动签发 Let's Encrypt 证书，<br>
          无需公网 80/443 入站可达，证书自动续期。
        </div>
        <div class="row" style="margin-top:8px">
          <input id="sslDnsEmail" type="email" placeholder="ACME 邮箱" value="${esc(st.email || '')}" style="flex:1">
        </div>
        <div class="row" style="margin-top:8px">
          <input id="sslDnsToken" type="password" placeholder="Cloudflare API Token (Zone:DNS:Edit)" style="flex:1">
        </div>
        <div class="row" style="margin-top:8px">
          <button onclick="${P}sslApplyDns01()" ${hasDns ? '' : 'disabled style="opacity:.5" title="当前 caddy 不支持 DNS-01，请先下载自定义版本"'}>启用 DNS-01</button>
          <button class="ghost" onclick="${P}sslDownloadCustomCaddy()">下载带 Cloudflare 插件的 Caddy</button>
        </div>
        <details style="margin-top:10px"><summary class="mut">操作步骤（点击展开）</summary>
          <ol class="mut" style="margin-top:6px;line-height:1.8">
            <li>点击「下载带 Cloudflare 插件的 Caddy」，获取自定义构建的二进制</li>
            <li>替换面板 caddy：<br>
              &nbsp;&nbsp;<code>cp /path/to/downloaded/caddy /opt/aups/runtime/caddy/caddy</code><br>
              &nbsp;&nbsp;<code>chmod +x /opt/aups/runtime/caddy/caddy</code><br>
              &nbsp;&nbsp;<code>systemctl restart caddy</code></li>
            <li>Cloudflare 面板 → SSL/TLS → Overview → 设为 <b>Full (strict)</b></li>
            <li>创建 API Token：My Profile → API Tokens → Create Token → Zone → DNS → Edit</li>
            <li>填入邮箱与 Token，点击「启用 DNS-01」</li>
            <li>验证：<code>curl -sk https://your.domain/</code> 应返回 200，且证书为 Let's Encrypt 签发</li>
          </ol>
        </details>
      </div>

      <div class="card"><h2>恢复默认</h2>
        <div class="mut" style="margin-bottom:8px">移除所有 SSL 特殊配置，恢复 Caddy 默认自动 HTTPS 行为（自动签发、HTTP→HTTPS 重定向）。</div>
        <button class="danger" onclick="${P}sslDisable()">恢复默认 HTTPS</button>
      </div>
      `;
    } catch (e) {
      view.innerHTML = navHtml() + errCard(e);
    }
  }
  async function sslApplyFlexible() {
    const email = document.getElementById('sslFlexEmail').value.trim();
    try {
      const r = await api('POST', '/api/caddy/ssl/flexible', { email });
      alert(r.message || '已启用 Flexible');
      await sslTab();
    } catch (e) { alert('启用失败：' + ((e && e.detail) || e)); }
  }
  async function sslApplyDns01() {
    const email = document.getElementById('sslDnsEmail').value.trim();
    const token = document.getElementById('sslDnsToken').value.trim();
    if (!token) return alert('请填写 Cloudflare API Token');
    if (!confirm('确定启用 DNS-01？将把 acme_dns cloudflare 写入 Caddyfile。')) return;
    try {
      const r = await api('POST', '/api/caddy/ssl/dns01', { email, api_token: token });
      alert(r.message || '已启用 DNS-01');
      await sslTab();
    } catch (e) { alert('启用失败：' + ((e && e.detail) || e)); }
  }
  async function sslDisable() {
    if (!confirm('确定恢复默认 HTTPS 行为？这会移除 Flexible/DNS-01 所有特殊配置。')) return;
    try {
      const r = await api('POST', '/api/caddy/ssl/disable');
      alert(r.message || '已恢复默认');
      await sslTab();
    } catch (e) { alert('恢复失败：' + ((e && e.detail) || e)); }
  }
  async function sslDownloadCustomCaddy() {
    if (!confirm('将从 caddy 官方 API 下载带 cloudflare DNS 插件的 linux/amd64 版本（约 40MB），继续？')) return;
    try {
      const r = await api('GET', '/api/caddy/ssl/caddy-with-cloudflare');
      alert('下载完成: ' + r.path + '\n\n请手动替换：\ncp ' + r.path + ' /opt/aups/runtime/caddy/caddy\nchmod +x /opt/aups/runtime/caddy/caddy\nsystemctl restart caddy');
      await sslTab();
    } catch (e) { alert('下载失败：' + ((e && e.detail) || e)); }
  }

  return {
    title: 'Caddy 环境',
    sections: [
      { id: 'caddyfile', title: 'Caddyfile 管理' },
      { id: 'instance', title: '实例控制' },
      { id: 'ssl', title: 'SSL 接入' },
    ],
    go: go,
    open: function (s) { go(s || 'caddyfile'); },
    caddyfileTab: caddyfileTab, siteNew: siteNew, siteEdit: siteEdit,
    siteUpdate: siteUpdate, siteDelete: siteDelete, siteCreate: siteCreate, siteClose: siteClose,
    caddyfileSave: caddyfileSave, caddyfileReload: caddyfileReload,
    cfPresets: cfPresets, cfInsertPreset: cfInsertPreset,
    instanceTab: instanceTab, inst: inst, caddyInstall: caddyInstall, caddyLogs: caddyLogs,
    sslTab: sslTab, sslApplyFlexible: sslApplyFlexible, sslApplyDns01: sslApplyDns01,
    sslDisable: sslDisable, sslDownloadCustomCaddy: sslDownloadCustomCaddy,
  };
})();
