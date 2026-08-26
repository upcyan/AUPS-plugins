/* AUPS 插件：harness-link — DeepSeek Harness 客户端通信桥
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 注意：插件名含连字符，内联事件统一用 AUPS_PLUGINS['harness-link'].xxx 括号访问。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['harness-link'] = (function () {
  const NS = "AUPS_PLUGINS['harness-link'].";
  let section = 'console';
  let cursor = 0;
  let pollTimer = null;
  let tick = 0;
  let connsCache = [];
  let selConn = '*';
  let tokenShown = false;

  function esc(s) {
    // 注意：实体名用拼接生成，避免源码中直接出现 &amp; 等序列
    return String(s == null ? '' : s).replace(/[&<>"']/g, m => (
      {'&': '&' + 'amp;', '<': '&' + 'lt;', '>': '&' + 'gt;',
       '"': '&' + 'quot;', "'": '&' + '#39;'}[m]));
  }
  function fmtTime(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    const p = n => String(n).padStart(2, '0');
    return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }

  function navHtml() {
    return `<div class="secnav">
      <button class="${section === 'console' ? 'on' : ''}" onclick="${NS}go('console')">通信台</button>
      <button class="${section === 'pairing' ? 'on' : ''}" onclick="${NS}go('pairing')">接入授权</button>
    </div>`;
  }

  function stopTimer() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

  function go(s) {
    section = s || section;
    stopTimer();
    if (section === 'pairing') pairingTab(); else consoleTab();
  }

  async function consoleTab() {
    cursor = 0;
    document.getElementById('view').innerHTML = navHtml() + `
      <div class="card">
        <h2>连接</h2>
        <div id="hlConns" class="row" style="flex-wrap:wrap;gap:8px"><span class="mut">加载中…</span></div>
        <div class="mut" style="font-size:11px;margin-top:8px">点击连接切换发送目标；离线连接超过心跳窗口后不再投递。没有连接？先到「接入授权」配对。</div>
      </div>
      <div class="card">
        <h2>消息</h2>
        <div id="hlMsgs" style="max-height:46vh;overflow:auto;display:flex;flex-direction:column;gap:8px"></div>
        <div class="row" style="margin-top:10px">
          <input id="hlInput" placeholder="输入发给 Harness 的消息…" style="flex:1"
                 onkeydown="if(event.key==='Enter'){event.preventDefault();${NS}sendMsg()}">
          <button onclick="${NS}sendMsg()">发送</button>
        </div>
      </div>`;
    await refreshAll();
    stopTimer();
    pollTimer = setInterval(async () => {
      tick++;
      try {
        await pullMessages();
        if (tick % 3 === 0) await refreshConns(true);
      } catch (e) { }
    }, 3000);
  }

  async function refreshAll() { await refreshConns(); await pullMessages(); }

  async function refreshConns(keep) {
    const st = await api('GET', '/api/hlink/status', null, true);
    connsCache = st.connections || [];
    const box = document.getElementById('hlConns');
    if (!box) return;
    if (!connsCache.length) {
      box.innerHTML = '<span class="mut">暂无连接。到「接入授权」页获取配对令牌，在 Harness 侧运行客户端脚本注册。</span>';
      return;
    }
    if (selConn !== '*' && !connsCache.some(c => c.id === selConn)) selConn = '*';
    box.innerHTML = connsCache.map(c =>
      `<button class="${selConn === c.id ? 'on' : 'ghost'}" style="${c.online ? '' : 'opacity:.55'}"
         onclick="${NS}pick('${esc(c.id)}')">${c.online ? '🟢' : '⚪'} ${esc(c.name)}${c.pending ? ' · 待投递' + c.pending : ''}</button>`
    ).join('') + `<button class="ghost" onclick="${NS}pick('*')">广播（在线）</button>`;
  }

  function pick(id) {
    selConn = id;
    refreshConns();
  }

  function bubble(m) {
    const out = m.dir === 'out';
    return `<div style="align-self:${out ? 'flex-end' : 'flex-start'};max-width:78%">
      <div style="background:var(--acc, #4f7cff);color:#fff;border-radius:10px;padding:8px 12px;white-space:pre-wrap;word-break:break-word">${esc(m.text)}</div>
      <div class="mut" style="font-size:11px;margin-top:2px;text-align:${out ? 'right' : 'left'}">${out ? '面板 → ' : ''}${esc(m.name || '')}${out ? '' : ' → 面板'} · ${fmtTime(m.ts)}${out && !m.delivered && m.id > 0 ? ' · 投递中' : ''}</div>
    </div>`;
  }

  async function pullMessages() {
    const d = await api('GET', '/api/hlink/messages?after=' + cursor + '&limit=300', null, true);
    if (d.cursor != null) cursor = Math.max(cursor, d.cursor); else if (d.messages && d.messages.length) cursor = d.messages[d.messages.length - 1].id;
    const box = document.getElementById('hlMsgs');
    if (!box) return;
    for (const m of (d.messages || [])) {
      const empty = box.querySelector('.hl-empty');
      if (empty) empty.remove();
      box.insertAdjacentHTML('beforeend', bubble(m));
    }
    if ((d.messages || []).length) box.scrollTop = box.scrollHeight;
    if (!box.children.length) {
      box.innerHTML = '<div class="mut hl-empty">还没有消息。在下方输入内容发给已连接的 Harness 客户端；客户端回复会实时出现在这里。</div>';
    }
  }

  async function sendMsg() {
    const inp = document.getElementById('hlInput');
    const text = (inp && inp.value || '').trim();
    if (!text) return;
    const target = selConn === '*' ? '*' : selConn;
    try {
      await api('POST', '/api/hlink/send', { conn_id: target, text });
      inp.value = '';
      await Promise.all([refreshConns(), pullMessages()]);
    } catch (e) { }
  }

  async function pairingTab() {
    stopTimer();
    tokenShown = false;
    document.getElementById('view').innerHTML = navHtml() + `
      <div class="card">
        <h2>配对令牌</h2>
        <div class="row" style="align-items:center;gap:8px">
          <code id="hlToken" style="flex:1;background:rgba(127,127,127,.12);padding:8px 10px;border-radius:8px;user-select:all">••••••••••••••••••••••••</code>
          <button class="ghost" onclick="${NS}revealToken()">显示</button>
          <button class="ghost" onclick="${NS}copyToken()">复制</button>
          <button onclick="${NS}rotateToken()">轮换令牌</button>
        </div>
        <div class="mut" style="font-size:11px;margin-top:6px">令牌仅用于客户端 register 时换取会话密钥；泄露请立即轮换（已建立的会话不受影响）。</div>
      </div>
      <div class="card">
        <h2>客户端接入</h2>
        <p><button class="ghost" onclick="${NS}dlClient()">⬇ 下载 harness_link_client.py</button>
        <span class="mut">零依赖，仅需 Python 3.8+（运行在 Harness 所在机器）</span></p>
        <ol style="line-height:2;margin:0">
          <li>复制上方配对令牌，在 Harness 所在机器下载并运行：
            <pre style="white-space:pre-wrap;background:rgba(127,127,127,.1);padding:8px;border-radius:8px;user-select:all">python harness_link_client.py register --server http://面板地址:端口 --token 配对令牌 --name "我的Harness"</pre></li>
          <li>常驻监听面板消息：
            <pre style="white-space:pre-wrap;background:rgba(127,127,127,.1);padding:8px;border-radius:8px;user-select:all">python harness_link_client.py listen --wait 15</pre></li>
          <li>回复面板：
            <pre style="white-space:pre-wrap;background:rgba(127,127,127,.1);padding:8px;border-radius:8px;user-select:all">python harness_link_client.py send --text "收到"</pre></li>
        </ol>
        <div class="mut" style="font-size:11px">安全提示：建议经 HTTPS 反代访问面板；HTTP 明文部署时令牌与消息可被链路窃听。</div>
      </div>
      <div class="card">
        <h2>已注册连接</h2>
        <div id="hlAdminConns"><span class="mut">加载中…</span></div>
      </div>`;
    await loadPairing();
    await loadAdminConns();
  }

  async function loadPairing() {
    const d = await api('GET', '/api/hlink/pairing');
    window.__hlToken = d.token;
    showTokenBox();
  }

  function showTokenBox() {
    const el = document.getElementById('hlToken');
    if (!el) return;
    el.textContent = tokenShown ? (window.__hlToken || '') : '•'.repeat(24);
  }

  async function revealToken() {
    tokenShown = !tokenShown;
    if (tokenShown && !window.__hlToken) await loadPairing(); else showTokenBox();
    const b = event && event.target;
    if (b) b.textContent = tokenShown ? '隐藏' : '显示';
  }

  async function copyToken() {
    if (!window.__hlToken) await loadPairing();
    try { await navigator.clipboard.writeText(window.__hlToken); alert('已复制'); }
    catch (e) { prompt('手动复制：', window.__hlToken || ''); }
  }

  async function rotateToken() {
    if (!confirm('轮换配对令牌？旧令牌立即失效（不影响已建立连接）。')) return;
    const d = await api('POST', '/api/hlink/pairing/rotate');
    window.__hlToken = d.token;
    showTokenBox();
    alert('已轮换');
  }

  async function dlClient() {
    try {
      const r = await fetch(location.origin + base() + '/api/hlink/client-script',
                            { headers: authHeaders() });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const blob = await r.blob();
      const aEl = document.createElement('a');
      aEl.href = URL.createObjectURL(blob);
      aEl.download = 'harness_link_client.py';
      document.body.appendChild(aEl); aEl.click(); aEl.remove();
      setTimeout(() => URL.revokeObjectURL(aEl.href), 4000);
    } catch (e) { alert('下载失败：' + ((e && e.message) || e)); }
  }

  function base() {
    const m = location.pathname.match(/^\/([^/]+)\//);
    return m ? '/' + m[1] : '';
  }
  function authHeaders() {
    let tok = '';
    try { tok = localStorage.getItem('aup_token') || ''; } catch (e) {}
    return { 'X-Auth-Token': tok };
  }

  async function loadAdminConns() {
    const st = await api('GET', '/api/hlink/status', null, true);
    connsCache = st.connections || [];
    const box = document.getElementById('hlAdminConns');
    if (!box) return;
    if (!connsCache.length) { box.innerHTML = '<span class="mut">暂无连接</span>'; return; }
    box.innerHTML = '<table style="width:100%;border-collapse:collapse;font-size:13px">' +
      '<tr class="mut" style="text-align:left"><th style="padding:4px">名称</th><th>状态</th><th>待投递</th><th>收/发</th><th>最后在线</th><th></th></tr>' +
      connsCache.map(c => `<tr>
        <td style="padding:4px">${esc(c.name)}<span class="mut" style="font-size:11px"> · ${esc(c.id)}</span></td>
        <td>${c.online ? '<span class="ok">在线</span>' : '<span class="mut">离线</span>'}</td>
        <td>${c.pending}</td>
        <td>${c.recv}/${c.sent}</td>
        <td class="mut">${c.last_seen ? new Date(c.last_seen * 1000).toLocaleString() : '-'}</td>
        <td><button class="ghost" onclick="${NS}delConn('${esc(c.id)}')">吊销</button></td>
      </tr>`).join('') + '</table>';
  }

  async function delConn(id) {
    if (!confirm('吊销该连接？其会话密钥立即失效，客户端需重新配对。')) return;
    try {
      await api('DELETE', '/api/hlink/connections/' + encodeURIComponent(id));
      await Promise.all([loadAdminConns(), refreshConns()]);
    } catch (e) { }
  }

  /* ---------- 总览卡片 ---------- */
  window.AUPS_CARDS = window.AUPS_CARDS || {};
  window.AUPS_CARDS['harness-link.status'] = {
    title: 'Harness 链接',
    source: 'harness-link',
    minW: 1, maxW: 3, w: 2,
    minH: 1, maxH: 2, h: 1,
    refresh: 20,
    render: async function (body) {
      let st = null;
      try {
        const r = await fetch(base() + '/api/hlink/status', { headers: authHeaders() });
        st = r.ok ? await r.json() : null;
      } catch (e) { st = null; }
      if (!st || !Array.isArray(st.connections)) {
        body.innerHTML = '<span class="mut">未登录或接口不可用</span>';
        return;
      }
      const rows = st.connections.slice(0, 5).map(c =>
        `<div style="display:flex;justify-content:space-between;gap:8px;font-size:13px;line-height:1.9">
          <span>${c.online ? '🟢' : '⚪'} ${esc(c.name)}${c.pending ? ' · 待投递' + c.pending : ''}</span>
          <span class="mut">${c.online ? '在线' : '离线'}</span>
        </div>`).join('');
      body.innerHTML =
        '<div style="display:flex;gap:16px;margin-bottom:4px">' +
        '<div><div style="font-size:22px;font-weight:600">' + (st.online || 0) + '</div><div class="mut" style="font-size:11px">在线连接 / 共 ' + st.connections_total + '</div></div>' +
        '<div><div style="font-size:22px;font-weight:600">' + (st.messages || 0) + '</div><div class="mut" style="font-size:11px">累计消息</div></div>' +
        '</div>' + rows +
        (st.connections.length ? '' : '<div class="mut" style="font-size:12px">暂无连接 · 插件中心 → Harness 通信桥 → 接入授权</div>');
    },
  };

  return {
    title: 'Harness 通信桥',
    sections: [
      { id: 'console', title: '通信台' },
      { id: 'pairing', title: '接入授权' },
    ],
    go: go,
    open: function (s) { go(s || 'console'); },
    consoleTab, pairingTab, pick, sendMsg,
    revealToken, copyToken, rotateToken, dlClient, delConn,
  };
})();
