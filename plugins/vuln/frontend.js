/* AUPS 插件：vuln —— 漏洞检测（系统 + 部署软件）
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 * 检测/修复在插件 scanner；报告数据层委托核心 aups.core.hostsec。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['vuln'] = (function () {
  const P = 'AUPS_PLUGINS.vuln.';

  async function overview() {
    const root = view('vuln');
    if (!root) return;
    root.innerHTML = `<div class="card" style="position:relative;z-index:1"><h2>漏洞检测</h2><span class="mut">加载中...</span></div>`;
    const st = await api('GET', '/api/vuln/status').catch(() => ({}));
    root.lastChild.innerHTML = `<h2>漏洞检测</h2>
      <div class="mut" style="margin-bottom:8px">检测系统待安全更新/补丁与部署软件漏洞（nginx/caddy/redis 等版本比对），检测到漏洞提示解决方案并可一键修复（装补丁 / 升级）。</div>
      <table style="min-width:320px">
        <tr><td>运行环境</td><td>${st.linux ? '<span class="ok">Linux 实机</span>' : '<span class="bad">非 Linux（检测将跳过）</span>'}</td></tr>
        <tr><td>包管理器</td><td>${esc(st.pm || '—')}</td></tr>
        <tr><td>部署软件监控数</td><td>${st.software_count || '—'}</td></tr>
        <tr><td>报告目录</td><td class="mut">${esc(st.reports_dir || '')}</td></tr>
      </table>
      <div class="row" style="flex-wrap:wrap;margin-top:10px">
        <button onclick="${P}run()">运行漏洞检测</button>
        <button class="ghost" onclick="${P}fixAll()">一键修复全部</button>
        <button class="ghost" onclick="${P}reports()">历史报告</button>
      </div>
      <div id="vulnOvBox" style="margin-top:10px"></div>`;
  }

  async function run() {
    const box = document.getElementById('vulnOvBox');
    if (!box) return;
    box.innerHTML = '<span class="mut">正在检测（查询安全更新与软件版本，可能耗时 1-2 分钟）...</span>';
    const r = await api('POST', '/api/vuln/check').catch(e => ({e: (e && e.message) || '失败'}));
    if (r.e) { box.innerHTML = '<span class="bad">检测失败：' + esc(r.e) + '</span>'; return; }
    renderResult(box, r);
  }

  function renderResult(box, r) {
    const checks = r.checks || [];
    const groups = {};
    checks.forEach(c => { (groups[c.group] = groups[c.group] || []).push(c); });
    const groupHtml = Object.entries(groups).map(([g, list]) => {
      const fail = list.filter(c => !c.ok).length;
      const rows = list.map(c => {
        const st = c.ok === undefined ? '<span class="mut">无法判定</span>'
          : c.ok ? '<span class="ok">正常</span>'
          : c.critical ? '<span class="bad">漏洞</span>' : '<span class="bad">需关注</span>';
        const fixBtn = (!c.ok && c.fixable)
          ? `<button class="ghost" onclick="${P}fixOne('${esc(c.pkg || '')}','${esc(c.title)}')">修复</button>` : '';
        return `<tr>
          <td>${esc(c.title)}</td>
          <td>${st}</td>
          <td class="mut" style="max-width:260px">${esc(c.current || '')}</td>
          <td class="mut" style="max-width:240px">${esc(c.expected || '')}</td>
          <td>${fixBtn}</td>
        </tr>`;
      }).join('');
      return `<h3 style="margin:12px 0 6px">${esc(g)}（${list.length - fail}/${list.length}）</h3>
        <table><tr><th>检测项</th><th>状态</th><th>当前</th><th>期望</th><th></th></tr>${rows}</table>`;
    }).join('');
    const crit = (r.critical || []).length;
    const fixable = (r.fixable || []).length;
    box.innerHTML = `<div class="mut">${esc(r.summary || '')}${crit ? ' <span class="bad">（' + crit + ' 项漏洞）</span>' : ''}${fixable ? ' <span class="ok">（' + fixable + ' 项可修复）</span>' : ''}</div>
      <div class="row" style="margin-top:6px">
        <button class="ghost" onclick="${P}fixAll()">一键修复全部</button>
        <button class="ghost" onclick="${P}opnReport('${esc(r.report_id || '')}')">查看报告</button>
      </div>
      ${groupHtml}`;
  }

  async function fixOne(pkg, title) {
    if (!confirm('修复：' + title + '（' + (pkg || '安全补丁') + '）？将调用系统包管理器升级对应软件。')) return;
    const box = document.getElementById('vulnOvBox');
    if (box) box.insertAdjacentHTML('beforeend', '<div class="mut" style="margin-top:6px">正在修复 ' + esc(title) + '...</div>');
    const r = await api('POST', '/api/vuln/fix', {scope: 'package', pkg: pkg}).catch(e => ({e: (e && e.message) || '失败'}));
    if (r && r.e) { alert('修复失败：' + r.e); return; }
    alert((r && r.summary) || '修复完成');
    if (box) box.innerHTML = '';
    run();
  }

  async function fixAll() {
    if (!confirm('一键修复全部：安装全部待安装的安全补丁 / 升级待更新软件？可能耗时较长。')) return;
    const box = document.getElementById('vulnOvBox');
    if (!box) return;
    box.innerHTML = '<span class="mut">正在安装安全补丁 / 升级软件（可能耗时数分钟）...</span>';
    const r = await api('POST', '/api/vuln/fix', {scope: 'security'}).catch(e => ({e: (e && e.message) || '失败'}));
    if (r && r.e) { box.innerHTML = '<span class="bad">修复失败：' + esc(r.e) + '</span>'; return; }
    if (!(r && r.ok)) { box.innerHTML = '<span class="bad">' + esc((r && r.summary) || '修复失败') + '</span>'; return; }
    box.innerHTML = '<span class="ok">' + esc((r && r.summary) || '修复完成') + '</span>';
    run();
  }

  async function reports() {
    const box = document.getElementById('vulnOvBox');
    if (!box) return;
    box.innerHTML = '<span class="mut">加载报告列表...</span>';
    const d = await api('GET', '/api/vuln/reports').catch(() => ({reports: []}));
    const rows = (d.reports || []).filter(r => r.tool === 'vuln').map(r => `<tr>
      <td>${esc(r.ts)}</td>
      <td class="mut">${esc(r.summary)}</td>
      <td><button class="ghost" onclick="${P}opnReport('${esc(r.id)}')">查看</button></td></tr>`).join('')
      || '<tr><td colspan="3" class="mut">暂无漏洞检测报告</td></tr>';
    box.innerHTML = `<div class="row" style="margin-bottom:6px"><button onclick="${P}run()">运行漏洞检测</button>&nbsp;<button class="ghost" onclick="${P}overview()">← 返回</button></div>
      <table><tr><th>时间</th><th>摘要</th><th></th></tr>${rows}</table>`;
  }

  async function opnReport(rid) {
    if (!rid) { const d = await api('GET', '/api/vuln/reports').catch(() => ({reports: []})); const rep = (d.reports || [])[0]; if (!rep) return alert('暂无报告'); rid = rep.id; }
    const d = await api('GET', '/api/vuln/report/' + encodeURIComponent(rid)).catch(e => ({e: (e && e.message) || '失败'}));
    if (d.e) return alert('读取失败：' + d.e);
    const res = d.result || {};
    const checks = res.checks || [];
    const rows = checks.map(c => `<tr>
      <td>${esc(c.title)}</td>
      <td>${c.ok === false ? (c.critical ? '<span class="bad">漏洞</span>' : '<span class="bad">需关注</span>') : '<span class="ok">正常</span>'}</td>
      <td class="mut">${esc(c.current || '')}</td>
      <td class="mut">${esc(c.advice || '')}</td></tr>`).join('') || '<tr><td colspan="4" class="mut">无检测项</td></tr>';
    const modal = document.createElement('div');
    modal.className = 'ov-modal';
    modal.innerHTML = `<div class="ov-modal-box" style="width:min(720px,92vw);max-height:70vh;overflow:auto">
      <h3>漏洞检测报告</h3>
      <div class="mut">${esc(d.ts || '')} · ${esc(res.summary || '')} · report ${esc(d.id || '')}</div>
      <table style="margin-top:8px"><tr><th>检测项</th><th>状态</th><th>当前</th><th>解决方案</th></tr>${rows}</table>
      <div class="row" style="margin-top:12px"><button class="ghost" onclick="this.closest('.ov-modal').remove()">关闭</button></div>
    </div>`;
    document.body.appendChild(modal);
  }

  return {
    title: '漏洞检测',
    sections: [{id: 'overview', title: '漏洞检测'}],
    go: overview,
    open: function (s) { overview(); },
    overview: overview, run: run, fixOne: fixOne, fixAll: fixAll, reports: reports, opnReport: opnReport
  };
})();