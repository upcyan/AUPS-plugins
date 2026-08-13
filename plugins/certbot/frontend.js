/* AUPS 插件：certbot —— Let's Encrypt 证书签发
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['certbot'] = (function () {
  const P = 'AUPS_PLUGINS.certbot.';

  async function mainTab() {
    const st = await api('GET', '/api/certbot/status');
    view.innerHTML = `
    <div class="card"><h2>Certbot 状态</h2>
      <div class="row">
        <span>状态: ${st.installed ? '<span class="ok">已安装</span>' : '<span class="bad">未检测到</span>'}</span>
        <span class="mut">${esc(st.version || '')}</span>
        <button onclick="${P}install()">${st.installed ? '重新检测' : '安装'}</button>
      </div>
      <div class="mut" style="margin-top:8px">证书目录: ${esc(st.data_dir || '-')}</div></div>
    <div class="card"><h2>申请证书</h2>
      <div class="row">
        <input id="certDomain" type="text" placeholder="域名，如 example.com" style="min-width:220px">
        <input id="certEmail" type="text" placeholder="联系邮箱" style="min-width:220px">
        <button onclick="${P}issue()">申请</button>
      </div>
      <div class="mut" style="margin-top:8px">standalone 验证需 80 端口可用；证书落在面板数据目录。</div>
      <pre id="certOut"></pre></div>`;
  }
  async function install() { await api('POST', '/api/certbot/install'); await mainTab(); }
  async function issue() {
    const domain = document.getElementById('certDomain').value.trim();
    const email = document.getElementById('certEmail').value.trim();
    if (!domain) { alert('请输入域名'); return; }
    const r = await api('POST', '/api/certbot/issue', { domain, email });
    if (r.cert) {
      document.getElementById('certOut').textContent = '证书: ' + r.cert + '\n私钥: ' + r.key;
      alert('申请成功：' + r.domain);
    } else {
      document.getElementById('certOut').textContent = JSON.stringify(r, null, 2);
      alert(r.message || '已完成');
    }
  }

  function go() { mainTab(); }

  return {
    title: 'Certbot',
    sections: [{ id: 'main', title: '证书签发' }],
    go: go,
    open: function () { go(); },
    mainTab: mainTab, install: install, issue: issue
  };
})();
