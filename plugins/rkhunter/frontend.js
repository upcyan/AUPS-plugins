/* AUPS 插件：rkhunter —— 主机入侵检测引擎（依赖插件）
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 * 逻辑委托核心 aups.core.hostsec（核心「安全引擎」页按需调用）。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['rkhunter'] = (function () {
  const P = 'AUPS_PLUGINS.rkhunter.';
  let section = 'overview';

  async function overview() {
    const root = view('rkhunter');
    if (!root) return;
    root.innerHTML = `<div class="card" style="position:relative;z-index:1"><h2>rkhunter</h2><span class="mut">加载中...</span></div>`;
    const st = await api('GET', '/api/rkhunter/status').catch(() => ({}));
    const inst = st.installed;
    root.lastChild.innerHTML = `<h2>rkhunter</h2>
      <table style="min-width:320px">
        <tr><td>状态</td><td>${inst ? '<span class="ok">已安装</span> <span class="mut">' + esc(st.version || '') + '</span>' : '<span class="bad">未安装</span>'}</td></tr>
        <tr><td>二进制</td><td class="mut">${esc(st.binary || '')}</td></tr>
      </table>
      <div class="mut" style="margin-top:8px">由面板 → 安全管理 → 安全加固 → 安全引擎页聚合调用；本页提供引擎独立管理。</div>
      <div class="row" style="flex-wrap:wrap;margin-top:10px">
        ${inst ? `<button class="ghost" onclick="${P}scan()">扫描</button>` : `<button onclick="${P}install()">安装</button>`}
        ${inst ? `<button class="ghost" onclick="${P}rein()">重装（强制）</button>` : ''}
        ${inst ? `<button class="danger" onclick="${P}uninst()">卸载</button>` : ''}
      </div>
      <div id="rkhOvBox" style="margin-top:10px"></div>`;
  }

  async function install() {
    if (!confirm('安装 rkhunter（需 root，调用系统包管理器）？')) return;
    const r = await api('POST', '/api/rkhunter/install').catch(e => ({e: (e && e.message) || '失败'}));
    alert(r.e ? ('失败：' + r.e) : (r.installed ? '安装成功' : '已发起安装'));
    await overview();
  }

  async function rein() {
    if (!confirm('强制重装 rkhunter：将先卸载已存在二进制再重装（插件受管）？')) return;
    const r = await api('POST', '/api/rkhunter/reinstall').catch(e => ({e: (e && e.message) || '失败'}));
    alert(r.e ? ('重装失败：' + r.e) : '已重装');
    await overview();
  }

  async function uninst() {
    if (!confirm('卸载 rkhunter 二进制？报告数据保留。')) return;
    await api('POST', '/api/rkhunter/uninstall').catch(e => alert('卸载失败：' + ((e && e.message) || e)));
    await overview();
  }

  async function scan() {
    const box = document.getElementById('rkhOvBox');
    if (!box) return;
    box.innerHTML = '<span class="mut">正在扫描（可能耗时数分钟）...</span>';
    const r = await api('POST', '/api/rkhunter/scan').catch(e => ({e: (e && e.message) || '失败'}));
    if (r.e) { box.innerHTML = '<span class="bad">扫描失败：' + esc(r.e) + '</span>'; return; }
    box.innerHTML = `<span class="ok">完成</span> <span class="mut">可疑 ${r.suspected || 0} · rootkit ${r.rootkits || 0}</span>
      <button class="ghost" onclick="${P}opnReport('')">查看报告</button>`;
  }

  async function opnReport(rid) {
    const d = await api('GET', '/api/rkhunter/reports').catch(() => ({reports: []}));
    const rep = (d.reports || [])[0];
    if (!rep) return alert('暂无报告');
    const full = await api('GET', '/api/rkhunter/report/' + encodeURIComponent(rep.id)).catch(e => ({e: (e && e.message) || '失败'}));
    const res = full.result || {};
    const modal = document.createElement('div');
    modal.className = 'ov-modal';
    modal.innerHTML = `<div class="ov-modal-box" style="width:min(640px,92vw);max-height:70vh;overflow:auto">
      <h3>rkhunter 扫描报告</h3>
      <div class="mut">${esc(full.ts || '')}</div>
      ${(res.warnings || []).map(w => `<div class="bad">${esc(w)}</div>`).join('') || '<span class="ok">未发现可疑项</span>'}
      <div class="row" style="margin-top:12px"><button class="ghost" onclick="this.closest('.ov-modal').remove()">关闭</button></div>
    </div>`;
    document.body.appendChild(modal);
  }

  return {
    title: 'rkhunter',
    sections: [{id: 'overview', title: 'rkhunter'}],
    go: overview,
    open: overview,
    overview: overview,
    install: install, rein: rein, uninst: uninst,
    scan: scan, opnReport: opnReport
  };
})();