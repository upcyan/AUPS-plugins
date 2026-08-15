/* AUPS 插件：yara —— YARA 引擎（规则扫描引擎依赖插件）
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / headers / alert / confirm。
 * 逻辑委托核心 aups.core.yara（规则数据由核心持有）。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['yara'] = (function () {
  const P = 'AUPS_PLUGINS.yara.';
  let section = 'overview';

  function navHtml() {
    return `<div class="secnav">
      <button class="${section === 'overview' ? 'on' : ''}" onclick="${P}go('overview')">引擎概览</button>
      <button class="${section === 'rules' ? 'on' : ''}" onclick="${P}go('rules')">规则订阅</button>
    </div>`;
  }

  async function overview() {
    const root = view('yara');
    if (!root) return;
    root.innerHTML = navHtml() + '<div class="card" style="position:relative;z-index:1"><span class="mut">加载中...</span></div>';
    const st = await api('GET', '/api/yara/status').catch(() => ({}));
    const inst = st.installed;
    const done = `<table style="min-width:320px">
      <tr><td>引擎</td><td><b>YARA</b></td></tr>
      <tr><td>状态</td><td>${inst ? '<span class="ok">已安装</span> <span class="mut">' + esc(st.version || '') + '</span>' : '<span class="bad">未安装</span>'}</td></tr>
      <tr><td>规则文件</td><td>${st.rules ? st.rules.count || 0 : 0} 个</td></tr>
      <tr><td>规则目录</td><td class="mut">${esc((st.rules && st.rules.dir) || '')}</td></tr>
      <tr><td>报告目录</td><td class="mut">${esc(st.reports_dir || '')}</td></tr>
    </table>
    <div class="row" style="margin-top:10px">
      ${inst ? `<button onclick="${P}scan()">快速扫描</button>` : `<button onclick="${P}install()">安装 YARA</button>`}
      <button class="ghost" onclick="${P}go('rules')">规则订阅</button>
    </div>
    <div id="yaraOvScan" style="margin-top:10px"></div>`;
    root.querySelector('.card').innerHTML = '<h2>引擎概览</h2>' + done;
  }

  async function install() {
    if (!confirm('安装 YARA（需 root，调用系统包管理器）？')) return;
    const r = await api('POST', '/api/yara/install').catch(e => ({e: (e && e.message) || '失败'}));
    alert(r.e ? ('安装失败：' + r.e) : (r.installed ? '安装成功：' + (r.version || '') : '已发起安装'));
    await overview();
  }

  async function scan() {
    const box = document.getElementById('yaraOvScan');
    if (!box) return;
    box.innerHTML = '<span class="mut">正在扫描（可能耗时数分钟）...</span>';
    const r = await api('POST', '/api/yara/scan').catch(e => ({e: (e && e.message) || '失败'}));
    if (r.e) { box.innerHTML = '<span class="bad">扫描失败：' + esc(r.e) + '</span>'; return; }
    box.innerHTML = `<span class="ok">完成</span> <span class="mut">${r.hits || 0} 命中 / ${r.files || 0} 路径 · ${r.rule_count || 0} 规则</span>
      <button class="ghost" onclick="${P}opnReport('${esc(r.report_id || '')}')">查看报告</button>`;
  }

  async function opnReport(rid) {
    if (!rid) return alert('无报告可查看');
    const d = await api('GET', '/api/yara/reports/' + encodeURIComponent(rid)).catch(e => ({e: (e && e.message) || '失败'}));
    if (d.e) return alert('读取失败：' + d.e);
    const res = d.result || {};
    const hits = (res.matches || []).slice(0, 50).map(m => `<div class="bad">${esc(m.rule)} · ${esc(m.match)} · ${esc(m.file)}</div>`).join('') || '<span class="ok">未命中</span>';
    const modal = document.createElement('div');
    modal.className = 'ov-modal';
    modal.innerHTML = `<div class="ov-modal-box" style="width:min(640px,92vw);max-height:70vh;overflow:auto">
      <h3>YARA 扫描报告</h3>
      <div class="mut">${esc(d.ts || '')}</div>${hits}
      <div class="row" style="margin-top:12px"><button class="ghost" onclick="this.closest('.ov-modal').remove()">关闭</button></div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function rules() {
    const root = view('yara');
    if (!root) return;
    root.innerHTML = navHtml() + '<div><span class="mut">加载中...</span></div>';
    const d = await api('GET', '/api/yara/subscribe').catch(() => ({subscriptions: []}));
    const rows = (d.subscriptions || []).map(s => `<tr>
      <td>${esc(s.name || s.url)}</td>
      <td class="mut" style="max-width:240px;overflow:hidden;text-overflow:ellipsis">${esc(s.url)}</td>
      <td>${s.enabled ? '<span class="ok">启用</span>' : '<span class="mut">停用</span>'}</td>
      <td>${s.rule_count || 0}</td>
      <td>${s.last_sync ? new Date(s.last_sync * 1000).toLocaleString() : '<span class="mut">未同步</span>'}</td>
      <td><div class="row"><button class="ghost" onclick="${P}sy('${esc(s.url)}')">同步</button>
        <button class="ghost" onclick="${P}del('${esc(s.url)}')">删除</button></div></td>
    </tr>`).join('') || '<tr><td colspan="6" class="mut">暂无订阅（默认内置 signature-base 精选规则）</td></tr>';
    root.lastChild.innerHTML = `<div class="card" style="position:relative;z-index:1">
      <h2>规则订阅</h2>
      <div class="mut" style="margin-bottom:8px">订阅远程 YARA 规则库，同步后用于扫描。核心主机安全与实时防护共用同一规则库。</div>
      <div class="row" style="flex-wrap:wrap">
        <input id="yarasubUrl" type="text" placeholder="规则 URL（.yar 文件）" style="flex:1;min-width:200px">
        <button onclick="${P}add()">添加订阅</button>
        <button class="ghost" onclick="${P}syncall()">同步全部</button>
      </div>
      <table style="margin-top:10px"><tr><th>名称</th><th>地址</th><th>状态</th><th>规则数</th><th>上次同步</th><th></th></tr>${rows}</table>
    </div>`;
  }

  async function add() {
    const el = document.getElementById('yarasubUrl');
    const url = el ? el.value.trim() : '';
    if (!url) return alert('请输入规则 URL');
    const r = await api('POST', '/api/yara/subscribe', {action: 'add', url}).catch(e => ({e: (e && e.message) || '失败'}));
    alert(r.e ? ('添加失败：' + r.e) : '已添加订阅');
    await rules();
  }

  async function del(url) {
    if (!confirm('删除订阅 ' + url + ' ？（已下载的规则文件也会删除）')) return;
    await api('POST', '/api/yara/subscribe', {action: 'remove', url});
    await rules();
  }

  async function sy(url) {
    const r = await api('POST', '/api/yara/subscribe/sync', {url}).catch(e => ({e: (e && e.message) || '失败'}));
    if (r.e) return alert('同步失败：' + r.e);
    const it = (r.synced || [])[0];
    alert(it ? (it.ok ? '同步成功，规则 ' + it.rule_count + ' 条' : '同步失败：' + (it.error || '')) : '无操作');
    await rules();
  }

  async function syncall() {
    const r = await api('POST', '/api/yara/subscribe/sync', {due_only: false}).catch(e => ({e: (e && e.message) || '失败'}));
    if (r.e) return alert('同步失败：' + r.e);
    const ok = (r.synced || []).filter(x => x.ok).length;
    alert('同步完成：成功 ' + ok + '，失败 ' + ((r.synced || []).length - ok));
    await rules();
  }

  function go(s) {
    section = s;
    s === 'rules' ? rules() : overview();
  }

  return {
    title: 'YARA 引擎',
    sections: [{id: 'overview', title: '引擎概览'}, {id: 'rules', title: '规则订阅'}],
    go: go,
    open: function (s) { go(s || 'overview'); },
    overview: overview, rules: rules,
    install: install, scan: scan, opnReport: opnReport,
    add: add, del: del, sy: sy, syncall: syncall
  };
})();