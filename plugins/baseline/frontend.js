/* AUPS 插件：baseline —— VPS 基线检查（纯只读审计）
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 * 检查项在插件 scanner；报告数据层委托核心 aups.core.hostsec。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['baseline'] = (function () {
  const P = 'AUPS_PLUGINS.baseline.';

  async function overview() {
    const root = view('baseline');
    if (!root) return;
    root.innerHTML = `<div class="card" style="position:relative;z-index:1"><h2>基线巡检</h2><span class="mut">加载中...</span></div>`;
    const st = await api('GET', '/api/baseline/status').catch(() => ({}));
    root.lastChild.innerHTML = `<h2>基线巡检</h2>
      <div class="mut" style="margin-bottom:8px">纯只读审计，不部署软件、不改系统配置。覆盖账号与权限 / 系统配置 / 内核网络加固 / 服务应用四类检查项，一键运行并生成报告。</div>
      <table style="min-width:320px">
        <tr><td>检查项数</td><td>${st.checks_count || '—'}</td></tr>
        <tr><td>运行环境</td><td>${st.linux ? '<span class="ok">Linux 实机</span>' : '<span class="bad">非 Linux（检查将跳过）</span>'}</td></tr>
        <tr><td>报告目录</td><td class="mut">${esc(st.reports_dir || '')}</td></tr>
      </table>
      <div class="row" style="flex-wrap:wrap;margin-top:10px">
        <button onclick="${P}run()">运行基线检查</button>
        <button class="ghost" onclick="${P}reports()">历史报告</button>
      </div>
      <div id="baselineOvBox" style="margin-top:10px"></div>`;
  }

  async function run() {
    const box = document.getElementById('baselineOvBox');
    if (!box) return;
    box.innerHTML = '<span class="mut">正在巡检（读取系统配置，通常数秒）...</span>';
    const r = await api('POST', '/api/baseline/check').catch(e => ({e: (e && e.message) || '失败'}));
    if (r.e) { box.innerHTML = '<span class="bad">检查失败：' + esc(r.e) + '</span>'; return; }
    renderResult(box, r);
  }

  function renderResult(box, r) {
    const checks = r.checks || [];
    const groups = {};
    checks.forEach(c => { (groups[c.group] = groups[c.group] || []).push(c); });
    const groupHtml = Object.entries(groups).map(([g, list]) => {
      const fail = list.filter(c => !c.ok).length;
      const rows = list.map(c => {
        const st = c.ok === undefined ? '<span class="mut">未决</span>'
          : c.ok ? '<span class="ok">通过</span>'
          : c.critical ? '<span class="bad">严重</span>' : '<span class="bad">未通过</span>';
        return `<tr>
          <td>${esc(c.title)}</td>
          <td>${st}</td>
          <td class="mut" style="max-width:360px">${esc(c.current || '')}</td>
          <td class="mut">${esc(c.expected || '')}</td>
        </tr>`;
      }).join('');
      return `<h3 style="margin:12px 0 6px">${esc(g)}（${list.length - fail}/${list.length}）</h3>
        <table><tr><th>检查项</th><th>状态</th><th>当前</th><th>期望</th></tr>${rows}</table>`;
    }).join('');
    const crit = (r.critical || []).length;
    box.innerHTML = `<div class="mut">${esc(r.summary || '')}${crit ? ' <span class="bad">（' + crit + ' 项严重）</span>' : ''}</div>
      <div class="row" style="margin-top:6px"><button class="ghost" onclick="${P}opnReport('${esc(r.report_id || '')}')">查看报告</button></div>
      ${groupHtml}`;
  }

  async function reports() {
    const box = document.getElementById('baselineOvBox');
    if (!box) return;
    box.innerHTML = '<span class="mut">加载报告列表...</span>';
    const d = await api('GET', '/api/baseline/reports').catch(() => ({reports: []}));
    const rows = (d.reports || []).filter(r => r.tool === 'baseline').map(r => `<tr>
      <td>${esc(r.ts)}</td>
      <td class="mut">${esc(r.summary)}</td>
      <td><button class="ghost" onclick="${P}opnReport('${esc(r.id)}')">查看</button></td></tr>`).join('')
      || '<tr><td colspan="3" class="mut">暂无基线检查报告</td></tr>';
    box.innerHTML = `<div class="row" style="margin-bottom:6px"><button onclick="${P}run()">运行基线检查</button>&nbsp;<button class="ghost" onclick="${P}overview()">← 返回</button></div>
      <table><tr><th>时间</th><th>摘要</th><th></th></tr>${rows}</table>`;
  }

  async function opnReport(rid) {
    if (!rid) { const d = await api('GET', '/api/baseline/reports').catch(() => ({reports: []})); const rep = (d.reports || [])[0]; if (!rep) return alert('暂无报告'); rid = rep.id; }
    const d = await api('GET', '/api/baseline/report/' + encodeURIComponent(rid)).catch(e => ({e: (e && e.message) || '失败'}));
    if (d.e) return alert('读取失败：' + d.e);
    const res = d.result || {};
    const checks = res.checks || [];
    const rows = checks.map(c => `<tr>
      <td>${esc(c.title)}</td>
      <td>${c.ok === false ? (c.critical ? '<span class="bad">严重</span>' : '<span class="bad">未通过</span>') : '<span class="ok">通过</span>'}</td>
      <td class="mut">${esc(c.current || '')}</td>
      <td class="mut">${esc(c.advice || '')}</td></tr>`).join('') || '<tr><td colspan="4" class="mut">无检查项</td></tr>';
    const modal = document.createElement('div');
    modal.className = 'ov-modal';
    modal.innerHTML = `<div class="ov-modal-box" style="width:min(700px,92vw);max-height:70vh;overflow:auto">
      <h3>VPS 基线检查报告</h3>
      <div class="mut">${esc(d.ts || '')} · ${esc(res.summary || '')} · report ${esc(d.id || '')}</div>
      <table style="margin-top:8px"><tr><th>检查项</th><th>状态</th><th>当前</th><th>建议</th></tr>${rows}</table>
      <div class="row" style="margin-top:12px"><button class="ghost" onclick="this.closest('.ov-modal').remove()">关闭</button></div>
    </div>`;
    document.body.appendChild(modal);
  }

  return {
    title: '基线检查',
    sections: [{id: 'overview', title: '基线巡检'}],
    go: overview,
    open: function (s) { overview(); },
    overview: overview, run: run, reports: reports, opnReport: opnReport
  };
})();