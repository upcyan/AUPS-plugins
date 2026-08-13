/* AUPS 插件：nginx —— Nginx 反代环境
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['nginx'] = (function () {
  const P = 'AUPS_PLUGINS.nginx.';

  async function mainTab() {
    const st = await api('GET', '/api/nginx/status');
    const dirs = `
      <tr><td>runtime（软件）</td><td class="mut">${esc(st.runtime_dir || '-')}</td></tr>
      <tr><td>config（配置）</td><td class="mut">${esc(st.config_dir || '-')}</td></tr>
      <tr><td>data（数据）</td><td class="mut">${esc(st.data_dir || '-')}</td></tr>`;
    view.innerHTML = `
    <div class="card"><h2>Nginx 状态</h2>
      <div class="row">
        <span>状态: ${st.installed ? '<span class="ok">已安装</span>' : '<span class="bad">未检测到</span>'}</span>
        <span class="mut">${esc(st.version || '')}</span>
        <button onclick="${P}install()">${st.installed ? '重新检测' : '安装/部署'}</button>
      </div></div>
    <div class="card"><h2>部署目录（面板目录下）</h2>
      <table><tr><th>类别</th><th>路径</th></tr>${dirs}</table>
      <div class="mut" style="margin-top:8px">证书申请请使用「certbot」或「acme」插件。</div></div>`;
  }
  async function install() { await api('POST', '/api/nginx/install'); await mainTab(); }

  function go() { mainTab(); }

  return {
    title: 'Nginx 环境',
    sections: [{ id: 'main', title: 'Nginx 反代' }],
    go: go,
    open: function () { go(); },
    mainTab: mainTab, install: install
  };
})();
