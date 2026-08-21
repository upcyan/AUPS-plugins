/* AUPS 插件：rkhunter 主机入侵检测引擎。 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS.rkhunter = (function () {
  const P = 'AUPS_PLUGINS.rkhunter.';
  function rootEl() { return document.getElementById('view'); }
  function errorHtml(e) { return `<div class="card"><h2>加载失败</h2><pre style="white-space:pre-wrap">${esc((e&&e.message)||e||'未知错误')}</pre></div>`; }

  async function overview() {
    const root = rootEl();
    if (!root) return;
    root.innerHTML = '<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try {
      const [st, rd] = await Promise.all([
        api('GET', '/api/rkhunter/status'), api('GET', '/api/rkhunter/reports').catch(() => ({reports:[]})),
      ]);
      const reports = rd.reports || [];
      const rows = reports.slice(0, 10).map(r => `<tr><td>${esc(r.ts||'-')}</td>
        <td class="mut">${esc(r.summary||'-')}</td><td><button class="ghost" onclick="${P}opnReport('${esc(r.id)}')">查看</button></td></tr>`).join('')
        || '<tr><td colspan="3" class="mut">暂无检测报告</td></tr>';
      root.innerHTML = `<div class="card"><h2>rkhunter · 主机入侵检测</h2>
        <div class="row" style="gap:18px;align-items:flex-start">
          <div><div class="mut">引擎状态</div><div>${st.installed?'<span class="ok">已安装</span>':'<span class="bad">未安装</span>'}</div></div>
          <div><div class="mut">版本</div><div>${esc(st.version||'-')}</div></div>
          <div><div class="mut">历史报告</div><div>${reports.length}</div></div>
          <div style="min-width:220px"><div class="mut">二进制</div><div style="word-break:break-all">${esc(st.binary||'-')}</div></div>
        </div>
        <div class="mut" style="margin-top:10px">检查 rootkit 特征、可疑系统文件、隐藏进程与异常配置。警告项需要结合服务器实际配置人工确认。</div>
        <div class="row" style="margin-top:12px">
          ${st.installed ? `<button onclick="${P}scan()">开始检测</button><button class="ghost" onclick="${P}rein()">重装引擎</button><button class="danger" onclick="${P}uninst()">卸载</button>` : `<button onclick="${P}install()">安装 rkhunter</button>`}
        </div><div id="rkhOvBox" style="margin-top:12px"></div>
      </div>
      <div class="card"><h2>最近报告</h2><div style="overflow-x:auto"><table>
        <thead><tr><th>时间</th><th>摘要</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
    } catch(e) { root.innerHTML = errorHtml(e); }
  }

  async function install() {
    if (!confirm('安装 rkhunter？将调用系统包管理器。')) return;
    try { await api('POST','/api/rkhunter/install'); alert('rkhunter 安装完成'); await overview(); }
    catch(e) { alert('安装失败：'+((e&&e.message)||e)); }
  }
  async function rein() {
    if (!confirm('重装 rkhunter？现有报告会保留。')) return;
    try { await api('POST','/api/rkhunter/reinstall'); alert('rkhunter 重装完成'); await overview(); }
    catch(e) { alert('重装失败：'+((e&&e.message)||e)); }
  }
  async function uninst() {
    if (!confirm('卸载 rkhunter 二进制？检测报告会保留。')) return;
    try { await api('POST','/api/rkhunter/uninstall'); await overview(); }
    catch(e) { alert('卸载失败：'+((e&&e.message)||e)); }
  }
  async function scan() {
    const box = document.getElementById('rkhOvBox');
    if (!box) return;
    box.innerHTML = '<div class="mut"><span class="spinner"></span> 正在检查主机，可能耗时数分钟...</div>';
    try {
      const r = await api('POST','/api/rkhunter/scan',{});
      const warn = (r.warnings||[]).map(line=>`<div class="bad" style="word-break:break-all">${esc(line)}</div>`).join('');
      box.innerHTML = `<div class="row" style="gap:18px"><div><span class="mut">可疑项</span> <b class="${r.suspected?'bad':'ok'}">${r.suspected||0}</b></div>
        <div><span class="mut">rootkit 警告</span> <b class="${r.rootkits?'bad':'ok'}">${r.rootkits||0}</b></div>
        <div><span class="mut">退出码</span> ${r.returncode}</div></div>
        ${r.error?`<div class="bad" style="margin-top:8px">${esc(r.error)}</div>`:''}
        ${warn||'<div class="ok" style="margin-top:8px">未发现 rkhunter 警告</div>'}
        <div class="row" style="margin-top:10px"><button class="ghost" onclick="${P}opnReport('${esc(r.report_id||'')}')">查看完整报告</button></div>`;
    } catch(e) { box.innerHTML='<span class="bad">检测失败：'+esc((e&&e.message)||e)+'</span>'; }
  }
  async function opnReport(rid) {
    try {
      if (!rid) {
        const d=await api('GET','/api/rkhunter/reports');
        if (!(d.reports||[]).length) return alert('暂无 rkhunter 报告');
        rid=d.reports[0].id;
      }
      const full=await api('GET','/api/rkhunter/report/'+encodeURIComponent(rid));
      const res=full.result||{};
      const modal=document.createElement('div'); modal.className='ov-modal';
      modal.innerHTML=`<div class="ov-modal-box" style="width:min(760px,94vw);max-height:80vh;overflow:auto">
        <h3>rkhunter 检测报告</h3><div class="mut">${esc(full.ts||'')} · exit ${res.returncode}</div>
        <div class="row" style="margin:10px 0"><span>可疑 ${res.suspected||0}</span><span>rootkit ${res.rootkits||0}</span></div>
        ${(res.warnings||[]).map(w=>`<div class="bad" style="word-break:break-all">${esc(w)}</div>`).join('')||'<span class="ok">未发现警告</span>'}
        <details style="margin-top:10px"><summary>原始输出</summary><pre style="white-space:pre-wrap">${esc(res.raw||'')}</pre></details>
        <div class="row" style="margin-top:12px"><button class="ghost" onclick="this.closest('.ov-modal').remove()">关闭</button></div></div>`;
      document.body.appendChild(modal);
    } catch(e) { alert('读取报告失败：'+((e&&e.message)||e)); }
  }
  return {title:'rkhunter',sections:[{id:'overview',title:'检测与报告'}],go:overview,open:overview,overview,install,rein,uninst,scan,opnReport};
})();
