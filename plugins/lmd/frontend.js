/* AUPS 插件：LMD (maldet) 恶意软件扫描引擎。 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS.lmd = (function () {
  const P = 'AUPS_PLUGINS.lmd.';
  let section = 'overview';

  function rootEl() { return document.getElementById('view'); }
  function navHtml() {
    return `<div class="secnav">
      <button class="${section === 'overview' ? 'on' : ''}" onclick="${P}go('overview')">扫描与报告</button>
      <button class="${section === 'quarantine' ? 'on' : ''}" onclick="${P}go('quarantine')">隔离区</button>
    </div>`;
  }
  function errorHtml(e) {
    return `<div class="card"><h2>加载失败</h2><pre style="white-space:pre-wrap">${esc((e&&e.message)||e||'未知错误')}</pre></div>`;
  }

  async function overview() {
    section = 'overview';
    const root = rootEl();
    if (!root) return;
    root.innerHTML = navHtml() + '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const [st, rd] = await Promise.all([
        api('GET', '/api/lmd/status'), api('GET', '/api/lmd/reports').catch(() => ({reports:[]})),
      ]);
      const reports = rd.reports || [];
      const paths = st.default_paths || [];
      const reportRows = reports.slice(0, 8).map(r => `<tr>
        <td>${esc(r.ts || '-')}</td><td class="mut">${esc(r.summary || '-')}</td>
        <td><button class="ghost" onclick="${P}opnReport('${esc(r.id)}')">查看</button></td></tr>`).join('')
        || '<tr><td colspan="3" class="mut">暂无扫描报告</td></tr>';
      root.innerHTML = navHtml() + `
        <div class="card"><h2>LMD · 恶意软件扫描</h2>
          <div class="row" style="gap:18px;align-items:flex-start">
            <div><div class="mut">引擎状态</div><div>${st.installed ? '<span class="ok">已安装</span>' : '<span class="bad">未安装</span>'}</div></div>
            <div><div class="mut">版本</div><div>${esc(st.version || '-')}</div></div>
            <div><div class="mut">历史报告</div><div>${reports.length}</div></div>
            <div style="min-width:220px"><div class="mut">二进制</div><div style="word-break:break-all">${esc(st.binary || '-')}</div></div>
          </div>
          <div class="row" style="margin-top:12px">
            ${st.installed ? `<button onclick="${P}scan()">开始扫描</button><button class="ghost" onclick="${P}rein()">重装引擎</button><button class="danger" onclick="${P}uninst()">卸载</button>` : `<button onclick="${P}install()">安装 LMD</button>`}
            <button class="ghost" onclick="${P}quar()">查看隔离区</button>
          </div>
        </div>
        ${st.installed ? `<div class="card"><h2>扫描设置</h2>
          <div class="blk"><span class="mut">扫描路径（逗号或换行分隔）</span>
            <textarea id="lmdPaths" rows="3" style="width:100%;font-family:monospace">${esc(paths.join('\n'))}</textarea></div>
          <label class="pc-chk"><input id="lmdQuarantine" type="checkbox" checked> 检出后按扫描报告自动隔离</label>
          <div id="lmdOvBox" style="margin-top:12px"></div>
        </div>` : ''}
        <div class="card"><h2>最近报告</h2><div style="overflow-x:auto">
          <table><thead><tr><th>时间</th><th>摘要</th><th></th></tr></thead><tbody>${reportRows}</tbody></table>
        </div></div>`;
    } catch (e) { root.innerHTML = navHtml() + errorHtml(e); }
  }

  async function install() {
    if (!confirm('安装 LMD？将下载官方安装包并部署到 /usr/local。')) return;
    try { await api('POST', '/api/lmd/install'); alert('LMD 安装完成'); await overview(); }
    catch(e) { alert('安装失败：' + ((e&&e.message)||e)); }
  }
  async function rein() {
    if (!confirm('重装 LMD？将先卸载现有引擎，扫描报告仍会保留。')) return;
    try { await api('POST', '/api/lmd/reinstall'); alert('LMD 重装完成'); await overview(); }
    catch(e) { alert('重装失败：' + ((e&&e.message)||e)); }
  }
  async function uninst() {
    if (!confirm('卸载 LMD 二进制与引擎隔离目录？面板扫描报告会保留。')) return;
    try { await api('POST', '/api/lmd/uninstall'); await overview(); }
    catch(e) { alert('卸载失败：' + ((e&&e.message)||e)); }
  }

  async function scan() {
    const box = document.getElementById('lmdOvBox');
    const input = document.getElementById('lmdPaths');
    if (!box || !input) return;
    const paths = input.value.split(/[\n,]+/).map(x => x.trim()).filter(Boolean);
    if (!paths.length) { alert('请至少填写一个扫描路径'); return; }
    box.innerHTML = '<div class="mut"><span class="spinner"></span> 正在扫描，路径较大时可能耗时数分钟...</div>';
    try {
      const r = await api('POST', '/api/lmd/scan', {paths, quarantine: !!document.getElementById('lmdQuarantine').checked});
      const found = (r.found || []).map(line => `<div class="bad" style="word-break:break-all">${esc(line)}</div>`).join('');
      const errors = (r.errors || []).map(line => `<div class="bad">${esc(line)}</div>`).join('');
      box.innerHTML = `<div class="row" style="gap:18px">
          <div><span class="mut">扫描文件</span> <b>${r.files || 0}</b></div>
          <div><span class="mut">命中</span> <b class="${r.hits ? 'bad' : 'ok'}">${r.hits || 0}</b></div>
          <div><span class="mut">已隔离</span> <b>${r.quarantined || 0}</b></div>
        </div>${found || '<div class="ok" style="margin-top:8px">未发现恶意文件</div>'}${errors}
        <div class="row" style="margin-top:10px"><button class="ghost" onclick="${P}opnReport('${esc(r.report_id || '')}')">查看完整报告</button></div>`;
    } catch(e) { box.innerHTML = '<span class="bad">扫描失败：' + esc((e&&e.message)||e) + '</span>'; }
  }

  async function opnReport(rid) {
    try {
      if (!rid) {
        const list = await api('GET', '/api/lmd/reports');
        if (!(list.reports || []).length) return alert('暂无 LMD 报告');
        rid = list.reports[0].id;
      }
      const full = await api('GET', '/api/lmd/report/' + encodeURIComponent(rid));
      const res = full.result || {};
      const modal = document.createElement('div');
      modal.className = 'ov-modal';
      modal.innerHTML = `<div class="ov-modal-box" style="width:min(760px,94vw);max-height:80vh;overflow:auto">
        <h3>LMD 扫描报告</h3><div class="mut">${esc(full.ts || '')} · ${esc((res.scan_ids || []).join(', '))}</div>
        <div class="row" style="margin:10px 0"><span>文件 ${res.files||0}</span><span class="${res.hits?'bad':'ok'}">命中 ${res.hits||0}</span><span>隔离 ${res.quarantined||0}</span></div>
        ${(res.found || []).map(w => `<div class="bad" style="word-break:break-all">${esc(w)}</div>`).join('') || '<span class="ok">未发现恶意文件</span>'}
        <details style="margin-top:10px"><summary>原始输出</summary><pre style="white-space:pre-wrap">${esc(res.raw || '')}</pre></details>
        <div class="row" style="margin-top:12px"><button class="ghost" onclick="this.closest('.ov-modal').remove()">关闭</button></div></div>`;
      document.body.appendChild(modal);
    } catch(e) { alert('读取报告失败：' + ((e&&e.message)||e)); }
  }

  async function quar() {
    section = 'quarantine';
    const root = rootEl();
    if (!root) return;
    root.innerHTML = navHtml() + '<div class="card"><span class="spinner"></span> 加载隔离区...</div>';
    try {
      const d = await api('GET', '/api/lmd/quarantine');
      const rows = (d.items || []).map(i => {
        const arg = encodeURIComponent(i.name).replace(/'/g, '%27');
        return `<tr><td style="word-break:break-all">${esc(i.name)}</td><td>${fmt(i.size)}</td>
          <td><button class="ghost danger" onclick="${P}restore('${arg}')">恢复</button></td></tr>`;
      }).join('') || '<tr><td colspan="3" class="mut">隔离区为空</td></tr>';
      root.innerHTML = navHtml() + `<div class="card"><h2>LMD 隔离区</h2>
        <div class="mut" style="margin-bottom:10px">恢复会将可疑文件放回原位置，请确认误报后再操作。</div>
        <div style="overflow-x:auto"><table><thead><tr><th>文件</th><th>大小</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
      </div>`;
    } catch(e) { root.innerHTML = navHtml() + errorHtml(e); }
  }
  async function restore(encodedName) {
    const name = decodeURIComponent(encodedName);
    if (!confirm('确认恢复隔离文件 ' + name + '？')) return;
    try { await api('POST', '/api/lmd/quarantine/restore', {name}); alert('已恢复：' + name); await quar(); }
    catch(e) { alert('恢复失败：' + ((e&&e.message)||e)); }
  }
  function go(s) { section = s || 'overview'; return section === 'quarantine' ? quar() : overview(); }

  return {
    title: 'LMD', sections: [{id:'overview',title:'扫描与报告'},{id:'quarantine',title:'隔离区'}],
    go, open: go, overview, quar, install, rein, uninst, scan, opnReport, restore
  };
})();
