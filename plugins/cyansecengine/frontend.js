/* AUPS 插件：cyansecengine —— 安全加固
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 *
 * 子页：安全概览（引擎状态/一键安装/快速扫描） / 扫描 / 隔离区 / 规则订阅。
 * 引擎均为按需扫描（rkhunter / LMD / YARA），无常驻进程，适配小内存 VPS。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['cyansecengine'] = (function () {
  const P = 'AUPS_PLUGINS.cyansecengine.';
  let section = 'overview';

  function navHtml() {
    return `<div class="secnav">
      <button class="${section === 'overview' ? 'on' : ''}" onclick="${P}go('overview')">安全概览</button>
      <button class="${section === 'scan' ? 'on' : ''}" onclick="${P}go('scan')">扫描</button>
      <button class="${section === 'quarantine' ? 'on' : ''}" onclick="${P}go('quarantine')">隔离区</button>
      <button class="${section === 'rules' ? 'on' : ''}" onclick="${P}go('rules')">规则订阅</button>
    </div>`;
  }

  function go(s) {
    section = s || 'overview';
    if (section === 'overview') overviewTab();
    else if (section === 'scan') scanTab();
    else if (section === 'quarantine') quarantineTab();
    else if (section === 'rules') rulesTab();
  }

  /* ---------- 安全概览 ---------- */
  async function overviewTab() {
    const d = await api('GET', '/api/cyansec/status').catch(() => ({}));
    const tools = d.rkhunter || {}, lmd = d.lmd || {}, yara = d.yara || {};
    const rules = d.rules || {};
    const toolRow = (name, st) => `<tr>
      <td>${esc(name)}</td>
      <td>${st.installed ? '<span class="ok">已安装</span>' : '<span class="bad">未安装</span>'} ${st.installed && st.version ? '<span class="mut">' + esc(st.version) + '</span>' : ''}</td>
      <td>${st.installed ? '<span class="mut">就绪</span>' : `<button class="ghost" onclick="${P}installTool('${esc(name)}')">安装</button>`}</td>
    </tr>`;
    view.innerHTML = navHtml() + `
    <div class="card"><h2>安全加固 · 引擎状态</h2>
      <table><tr><th>引擎</th><th>状态</th><th>操作</th></tr>
        ${toolRow('rkhunter', tools)}
        ${toolRow('lmd', lmd)}
        ${toolRow('yara', yara)}
      </table>
      <div class="mut" style="margin-top:8px">规则文件: <b>${rules.count || 0}</b> 个 · ${esc(rules.dir || '')}</div>
    </div>
    <div class="card"><h2>快速扫描</h2>
      <div class="row" style="flex-wrap:wrap">
        <button onclick="${P}runScan('rkhunter')">rkhunter 入侵检测</button>
        <button onclick="${P}runScan('lmd')">LMD 恶意文件扫描</button>
        <button onclick="${P}runScan('yara')">YARA 规则扫描</button>
        <button class="ghost" onclick="${P}runScan('lmd')">扫描面板数据目录</button>
      </div>
      <div class="mut" style="margin-top:8px">按需运行，不常驻进程。扫描结果自动保存为报告，可在「扫描」页查看。</div>
      <div id="ovScanBox"></div>
    </div>`;
  }
  async function installTool(tool) {
    if (!confirm('安装 ' + tool + '（需 root，可能调用系统包管理器或下载）？')) return;
    const r = await api('POST', '/api/cyansec/install', {tool});
    alert((r.ok ? '安装成功：' : '') + tool + ((r && r.version) ? ' ' + r.version : ''));
    await overviewTab();
  }
  async function runScan(tool) {
    const box = document.getElementById('ovScanBox');
    if (box) box.innerHTML = '<div class="mut">正在运行 ' + esc(tool) + ' 扫描（可能耗时数分钟）...</div>';
    try {
      const r = await api('POST', '/api/cyansec/scan', {tool: tool});
      const sum = r.summary || (r.warnings ? '可疑项 ' + r.suspected : '');
      if (box) box.innerHTML = `<div class="card"><h2>${esc(tool)} 扫描完成</h2>
        <div class="mut">${esc(sum)}</div>
        <div class="row" style="margin-top:8px"><button class="ghost" onclick="${P}openReport('${esc(r.report_id)}')">查看报告</button></div></div>`;
      alert(tool + ' 扫描完成');
    } catch (e) {
      if (box) box.innerHTML = '';
      alert('扫描失败：' + ((e && e.message) || e));
    }
  }
  function openReport(rid) {
    api('GET', '/api/cyansec/reports/' + rid).then(d => {
      const res = d.result || {};
      const warnHtml = (res.warnings || []).map(w => `<div>${esc(w)}</div>`).join('') || '';
      const foundHtml = (res.found || []).map(w => `<div class="bad">${esc(w)}</div>`).join('') || '';
      const matchHtml = (res.matches || []).map(m => `<div><span class="bad">${esc(m.match)}</span> <span class="mut">${esc(m.file)}</span>（规则 ${esc(m.rule)}）</div>`).join('') || '';
      const modal = document.createElement('div');
      modal.className = 'ov-modal';
      modal.innerHTML = `<div class="ov-modal-box" style="width:min(620px,92vw);max-height:70vh;overflow:auto">
        <h3>扫描报告 · ${esc(d.tool)}</h3>
        <div class="mut">${esc(d.ts)} · report ${esc(d.id)}</div>
        ${warnHtml || foundHtml || matchHtml || '<div class="ok" style="margin-top:8px">未发现可疑项</div>'}
        ${res.raw ? `<div class="mut" style="margin-top:10px;font-size:11px"><pre>${esc(res.raw.slice(0, 1500))}</pre></div>` : ''}
        <div class="row" style="margin-top:12px"><button class="ghost" onclick="this.closest('.ov-modal').remove()">关闭</button></div>
      </div>`;
      document.body.appendChild(modal);
    }).catch(e => alert('读取报告失败：' + ((e && e.message) || e)));
  }

  /* ---------- 扫描 ---------- */
  async function scanTab() {
    const [st, reps] = await Promise.all([
      api('GET', '/api/cyansec/status').catch(() => ({})),
      api('GET', '/api/cyansec/reports').catch(() => ({reports: []}))
    ]);
    const rows = (reps.reports || []).map(r => `<tr>
      <td>${esc(r.ts)}</td><td>${esc(r.tool)}</td><td class="mut">${esc(r.summary)}</td>
      <td><button class="ghost" onclick="${P}openReport('${esc(r.id)}')">查看</button></td></tr>`).join('')
      || '<tr><td colspan="4" class="mut">暂无扫描记录</td></tr>';
    const engines = [['rkhunter','入侵检测（rootkit/后门）'],['lmd','恶意文件/Webshell 扫描'],['yara','自定义/订阅规则匹配']];
    const scanCards = engines.map(([t, d]) => {
      const st_ = st[t] || {};
      return `<div class="card"><h2>${esc(t)}</h2>
        <div class="mut">${esc(d)}</div>
        <div class="mut">状态: ${st_.installed ? '<span class="ok">已安装</span>' : '<span class="bad">未安装</span>'}</div>
        <div class="row" style="margin-top:8px">
          <button ${st_.installed ? '' : 'disabled'} onclick="${P}scanWith('${esc(t)}')">扫描默认路径</button>
          <input type="text" placeholder="自定义路径，空格分隔" style="flex:1;min-width:140px">
          <button class="ghost" ${st_.installed ? '' : 'disabled'} onclick="${P}scanCustom('${esc(t)}',this)">扫描指定</button>
        </div>
        <div id="scanBox_${esc(t)}"></div></div>`;
    }).join('');
    view.innerHTML = navHtml() + `<div class="card"><h2>历史扫描报告</h2>
      <table><tr><th>时间</th><th>引擎</th><th>摘要</th><th></th></tr>${rows}</table></div>
      ${scanCards}`;
  }
  async function scanWith(tool) {
    const box = document.getElementById('scanBox_' + tool);
    if (box) box.innerHTML = '<div class="mut">扫描进行中...</div>';
    const r = await api('POST', '/api/cyansec/scan', {tool: tool});
    if (box) box.innerHTML = `<div class="ok">完成（report ${esc(r.report_id)}）</div>`;
    alert(tool + ' 扫描完成');
    await scanTab();
  }
  async function scanCustom(tool, btn) {
    const input = btn.previousElementSibling;
    const paths = (input.value || '').split(/\s+/).filter(Boolean);
    if (!paths.length) { alert('请输入扫描路径'); return; }
    const box = document.getElementById('scanBox_' + tool);
    if (box) box.innerHTML = '<div class="mut">扫描进行中...</div>';
    const r = await api('POST', '/api/cyansec/scan', {tool: tool, paths: paths});
    if (box) box.innerHTML = `<div class="ok">完成（report ${esc(r.report_id)}）</div>`;
    alert(tool + ' 扫描完成');
    await scanTab();
  }

  /* ---------- 隔离区 ---------- */
  async function quarantineTab() {
    const d = await api('GET', '/api/cyansec/quarantine').catch(() => ({items: []}));
    const rows = (d.items || []).map(i => `<tr>
      <td>${esc(i.name)}</td><td>${fmt(i.size)}</td>
      <td><button class="ghost" onclick="${P}restoreQ('${esc(i.name)}')">恢复</button></td></tr>`).join('')
      || '<tr><td colspan="3" class="mut">隔离区为空（LMD 检测到的恶意文件会被移到这里）</td></tr>';
    view.innerHTML = navHtml() + `<div class="card"><h2>LMD 隔离区</h2>
      <table><tr><th>文件名</th><th>大小</th><th></th></tr>${rows}</table>
      <div class="mut" style="margin-top:8px">恢复操作把隔离文件放回原路径（谨慎：可能是恶意文件）。</div></div>`;
  }
  async function restoreQ(name) {
    if (!confirm('恢复隔离文件 ' + name + ' ？\n（该文件可能是恶意软件，请确认来源）')) return;
    await api('POST', '/api/cyansec/quarantine/restore', {name: name});
    alert('已恢复：' + name);
    await quarantineTab();
  }

  /* ---------- 规则订阅 ---------- */
  async function rulesTab() {
    const d = await api('GET', '/api/cyansec/subscribe').catch(() => ({subscriptions: []}));
    const subs = d.subscriptions || [];
    const rows = subs.map((s, i) => `<tr>
      <td>${esc(s.name || s.url)}</td>
      <td class="mut" style="max-width:260px;overflow:hidden;text-overflow:ellipsis">${esc(s.url)}</td>
      <td>${s.enabled ? '<span class="ok">启用</span>' : '<span class="mut">停用</span>'}</td>
      <td>${s.rule_count || 0}</td>
      <td>${s.last_sync ? new Date(s.last_sync * 1000).toLocaleString() : '<span class="mut">未同步</span>'}</td>
      <td><div class="row">
        <button class="ghost" onclick="${P}syncSub('${esc(s.url)}')">同步</button>
        <button class="ghost" onclick="${P}removeSub('${esc(s.url)}')">删除</button>
      </div></td></tr>`).join('') || '<tr><td colspan="6" class="mut">暂无订阅</td></tr>';
    view.innerHTML = navHtml() + `
    <div class="card"><h2>在线规则订阅</h2>
      <div class="mut" style="margin-bottom:8px">订阅远程 YARA 规则库，同步后用于 YARA 扫描。默认内置 signature-base（社区维护，含 webshell/挖矿/恶意样本特征）。</div>
      <div class="row" style="flex-wrap:wrap">
        <input type="text" placeholder="规则 URL（.yar 文件，GitHub raw 等）" style="flex:1;min-width:200px">
        <input type="text" placeholder="名称（可选）" style="min-width:120px">
        <input type="number" placeholder="同步间隔秒" value="86400" style="width:120px">
        <button onclick="${P}addSub()">添加订阅</button>
        <button class="ghost" onclick="${P}syncAllSub()">同步全部</button>
      </div>
      <table style="margin-top:10px"><tr><th>名称</th><th>地址</th><th>状态</th><th>规则数</th><th>上次同步</th><th></th></tr>${rows}</table>
      <div class="mut" style="margin-top:8px">也可把 .yar 规则文件直接放入 <code>${esc(d.rules_dir || 'data/cyansecengine/rules')}</code> 目录。</div>
    </div>`;
  }
  async function addSub() {
    const box = document.querySelector('.ov-modal-box, .card');
    const inputs = Array.from(document.querySelectorAll('input'));
    const urlIn = inputs.find(i => i.placeholder.includes('规则 URL'));
    const nameIn = inputs.find(i => i.placeholder === '名称（可选）');
    const intervalIn = inputs.find(i => i.placeholder === '同步间隔秒');
    const url = urlIn ? urlIn.value.trim() : '';
    if (!url) { alert('请输入规则 URL'); return; }
    const body = {action: 'add', url: url};
    if (nameIn && nameIn.value) body.name = nameIn.value.trim();
    if (intervalIn && intervalIn.value) body.interval = parseInt(intervalIn.value) || 86400;
    await api('POST', '/api/cyansec/subscribe', body);
    alert('已添加订阅');
    await rulesTab();
  }
  async function removeSub(url) {
    if (!confirm('删除订阅 ' + url + ' ？（已下载的规则文件也会删除）')) return;
    await api('POST', '/api/cyansec/subscribe', {action: 'remove', url: url});
    alert('已删除');
    await rulesTab();
  }
  async function syncSub(url) {
    const r = await api('POST', '/api/cyansec/subscribe/sync', {url: url});
    const it = (r.synced || [])[0];
    alert(it ? (it.ok ? '同步成功，规则 ' + it.rule_count + ' 条' : '同步失败：' + (it.error || '')) : '无操作');
    await rulesTab();
  }
  async function syncAllSub() {
    const r = await api('POST', '/api/cyansec/subscribe/sync', {due_only: false});
    const ok = (r.synced || []).filter(x => x.ok).length;
    const fail = (r.synced || []).length - ok;
    alert('同步完成：成功 ' + ok + '，失败 ' + fail);
    await rulesTab();
  }

  return {
    title: '安全加固',
    sections: [
      {id: 'overview', title: '安全概览'},
      {id: 'scan', title: '扫描'},
      {id: 'quarantine', title: '隔离区'},
      {id: 'rules', title: '规则订阅'},
    ],
    go: go,
    open: function (s) { go(s || 'overview'); },
    overviewTab: overviewTab, scanTab: scanTab, quarantineTab: quarantineTab, rulesTab: rulesTab,
    installTool: installTool, runScan: runScan, openReport: openReport,
    scanWith: scanWith, scanCustom: scanCustom, restoreQ: restoreQ,
    addSub: addSub, removeSub: removeSub, syncSub: syncSub, syncAllSub: syncAllSub,
  };
})();
