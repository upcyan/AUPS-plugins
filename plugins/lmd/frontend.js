/* AUPS 插件：lmd —— LMD (maldet) 恶意软件扫描引擎（依赖插件）
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 * 逻辑委托核心 aups.core.hostsec（核心「安全引擎」页按需调用）。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['lmd'] = (function () {
  const P = 'AUPS_PLUGINS.lmd.';
  let section = 'overview';

  async function overview() {
    const root = view('lmd');
    if (!root) return;
    root.innerHTML = `<div class="card" style="position:relative;z-index:1"><h2>LMD</h2><span class="mut">加载中...</span></div>`;
    const st = await api('GET', '/api/lmd/status').catch(() => ({}));
    const inst = st.installed;
    root.lastChild.innerHTML = `<h2>LMD (maldet)</h2>
      <table style="min-width:320px">
        <tr><td>状态</td><td>${inst ? '<span class="ok">已安装</span>' : '<span class="bad">未安装</span>'}</td></tr>
        <tr><td>二进制</td><td class="mut">${esc(st.binary || '')}</td></tr>
      </table>
      <div class="mut" style="margin-top:8px">由面板 → 安全管理 → 安全加固 → 安全引擎页聚合调用；本页提供引擎独立管理与隔离区。</div>
      <div class="row" style="flex-wrap:wrap;margin-top:10px">
        ${inst ? `<button class="ghost" onclick="${P}scan()">扫描</button>` : `<button onclick="${P}install()">安装</button>`}
        ${inst ? `<button class="ghost" onclick="${P}rein()">重装（强制）</button>` : ''}
        ${inst ? `<button class="danger" onclick="${P}uninst()">卸载</button>` : ''}
        <button class="ghost" onclick="${P}quar()">隔离区</button>
      </div>
      <div id="lmdOvBox" style="margin-top:10px"></div>`;
  }

  async function install() {
    if (!confirm('安装 LMD（需 root，下载官方 tarball 到 /usr/local）？')) return;
    const r = await api('POST', '/api/lmd/install').catch(e => ({e: (e && e.message) || '失败'}));
    alert(r.e ? ('失败：' + r.e) : (r.installed ? '安装成功' : '已发起安装'));
    await overview();
  }

  async function rein() {
    if (!confirm('强制重装 LMD：将先卸载已存在二进制再重装（插件受管）？')) return;
    const r = await api('POST', '/api/lmd/reinstall').catch(e => ({e: (e && e.message) || '失败'}));
    alert(r.e ? ('重装失败：' + r.e) : '已重装');
    await overview();
  }

  async function uninst() {
    if (!confirm('卸载 LMD 二进制与隔离目录？报告数据保留。')) return;
    await api('POST', '/api/lmd/uninstall').catch(e => alert('卸载失败：' + ((e && e.message) || e)));
    await overview();
  }

  async function scan() {
    const box = document.getElementById('lmdOvBox');
    if (!box) return;
    box.innerHTML = '<span class="mut">正在扫描（可能耗时数分钟）...</span>';
    const r = await api('POST', '/api/lmd/scan').catch(e => ({e: (e && e.message) || '失败'}));
    if (r.e) { box.innerHTML = '<span class="bad">扫描失败：' + esc(r.e) + '</span>'; return; }
    box.innerHTML = `<span class="ok">完成</span> <span class="mut">命中 ${r.hits || 0} · 隔离 ${r.quarantined || 0}</span>
      <button class="ghost" onclick="${P}opnReport('')">查看报告</button>`;
  }

  async function opnReport(rid) {
    const d = await api('GET', '/api/lmd/reports').catch(() => ({reports: []}));
    const rep = (d.reports || [])[0];
    if (!rep) return alert('暂无报告');
    const full = await api('GET', '/api/lmd/report/' + encodeURIComponent(rep.id)).catch(e => ({e: (e && e.message) || '失败'}));
    const res = full.result || {};
    const modal = document.createElement('div');
    modal.className = 'ov-modal';
    modal.innerHTML = `<div class="ov-modal-box" style="width:min(640px,92vw);max-height:70vh;overflow:auto">
      <h3>LMD 扫描报告</h3>
      <div class="mut">${esc(full.ts || '')}</div>
      ${(res.found || []).map(w => `<div class="bad">${esc(w)}</div>`).join('') || '<span class="ok">未发现可疑文件</span>'}
      <div class="row" style="margin-top:12px"><button class="ghost" onclick="this.closest('.ov-modal').remove()">关闭</button></div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function quar() {
    const root = view('lmd');
    if (!root) return;
    root.innerHTML = `<div class="card" style="position:relative;z-index:1"><h2>LMD 隔离区</h2><span class="mut">加载中...</span></div>`;
    const d = await api('GET', '/api/lmd/quarantine').catch(() => ({items: []}));
    const rows = (d.items || []).map(i => `<tr>
      <td>${esc(i.name)}</td><td>${fmt(i.size)}</td>
      <td><button class="ghost" onclick="${P}restore('${esc(i.name)}')">恢复</button></td></tr>`).join('')
      || '<tr><td colspan="3" class="mut">隔离区为空</td></tr>';
    root.lastChild.innerHTML = `<h2>LMD 隔离区</h2>
      <div class="mut" style="margin-bottom:8px">恢复操作把隔离文件放回原路径（谨慎：可能是恶意文件）。</div>
      <table><tr><th>文件名</th><th>大小</th><th></th></tr>${rows}</table>
      <div class="row" style="margin-top:10px"><button class="ghost" onclick="${P}overview()">返回引擎</button></div>`;
  }

  async function restore(name) {
    if (!confirm('恢复隔离文件 ' + name + ' ？（该文件可能是恶意软件，请确认来源）')) return;
    await api('POST', '/api/lmd/quarantine/restore', {name});
    alert('已恢复：' + name);
    await quar();
  }

  return {
    title: 'LMD',
    sections: [{id: 'overview', title: 'LMD'}, {id: 'quarantine', title: '隔离区'}],
    go: function (s) { s === 'quarantine' ? quar() : overview(); },
    open: function (s) { s === 'quarantine' ? quar() : overview(); },
    overview: overview, quar: quar,
    install: install, rein: rein, uninst: uninst,
    scan: scan, opnReport: opnReport, restore: restore
  };
})();