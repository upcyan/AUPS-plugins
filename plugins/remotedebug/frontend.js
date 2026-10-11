/* AUPS 插件：remotedebug —— 远程调试（只读命令通道）
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / view。
 *
 * 安全提示：本页只提供只读命令；服务端按命令目录 + 目录白名单 + 输出脱敏执行，
 * 前端不做任何安全判断（前端校验只是体验优化，不能作为安全边界）。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['remotedebug'] = (function () {
  const P = 'AUPS_PLUGINS.remotedebug.';
  let state = { status: null, sessions: [] };

  function fmtTs(ts) {
    if (!ts) return '-';
    const d = new Date(ts * 1000);
    const p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
      + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function leftTime(expiresAt) {
    const left = (expiresAt || 0) - Math.floor(Date.now() / 1000);
    if (left <= 0) return '<span class="bad">已过期</span>';
    const m = Math.floor(left / 60);
    return m >= 60 ? Math.floor(m / 60) + ' 小时 ' + (m % 60) + ' 分'
      : m + ' 分 ' + (left % 60) + ' 秒';
  }

  async function terminal() {
    const root = view('remotedebug');
    if (!root) return;
    root.innerHTML = '<div class="card"><h2>终端命令</h2>'
      + '<span class="mut">加载中...</span></div>';
    try {
      state.status = await api('GET', '/api/remotedebug/status');
      state.sessions = (await api('GET', '/api/remotedebug/sessions')).sessions || [];
    } catch (e) {
      root.innerHTML = '<div class="card"><h2>加载失败</h2><pre>'
        + esc((e && e.message) || e) + '</pre></div>';
      return;
    }
    render(root);
  }

  function render(root) {
    const st = state.status || {};
    const env = st.environment || {};
    const cat = st.catalog || {};
    const names = Object.keys(cat).sort();
    const chips = names.map(n =>
      `<button class="ghost" style="margin:2px;font-size:12px"
        title="${esc(cat[n].description)}"
        onclick="${P}fill('${esc(n)} ')">${esc(n)}</button>`).join('');
    const sessRows = (state.sessions || []).length
      ? state.sessions.map(s => `<tr>
          <td>${esc(s.label || '')}</td>
          <td class="mut">${esc(s.sid || '')}</td>
          <td>${leftTime(s.expires_at)}</td>
          <td class="mut" style="font-size:11px">${(s.roots || []).map(esc).join('<br>') || '（默认目录）'}</td>
          <td class="mut" style="font-size:11px">${(s.commands || []).map(esc).join(' ') || '全部只读'}</td>
          <td class="mut">${s.uses || 0}</td>
          <td><button class="ghost danger"
            onclick="${P}revoke('${esc(s.sid)}')">吊销</button></td>
        </tr>`).join('')
      : '<tr><td colspan="7" class="mut">当前无有效会话</td></tr>';

    root.innerHTML = `<div class="card"><h2>终端命令</h2>
      <div class="mut" style="margin-bottom:8px">
        只读通道：命令经白名单校验后执行，输出脱敏后展示。不支持写操作与交互式 shell。
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">${chips}</div>
      <textarea id="rdCmd" rows="6" spellcheck="false"
        placeholder="每行一条只读命令，例如：&#10;ls -l /opt/aups/config/caddy&#10;caddy validate --config /opt/aups/config/caddy/Caddyfile&#10;systemctl status caddy --no-pager"
        style="width:100%;box-sizing:border-box;font-family:ui-monospace,monospace;resize:vertical"></textarea>
      <div class="row" style="margin-top:8px;flex-wrap:wrap">
        <button onclick="${P}runExec()">执行</button>
        <button class="ghost" onclick="${P}clearOut()">清空输出</button>
        <span class="mut" style="font-size:12px">最多 ${esc(String(st.limits && st.limits.max_steps || 8))} 行 · 单行超时 ${esc(String(st.limits && st.limits.max_timeout || 30))}s</span>
      </div>
      <pre id="rdOut" style="margin-top:10px;max-height:52vh;overflow:auto;white-space:pre-wrap;word-break:break-all;background:rgba(0,0,0,.18);padding:10px;border-radius:6px;font-size:12px">（输出将显示在此）</pre>
      <div class="mut" style="font-size:11px;margin-top:6px">
        允许目录：${(st.roots || []).map(esc).join('、') || '-'}
        · 可用命令 ${esc(String((env.available || []).length))}/${esc(String(names.length))}
      </div>
    </div>

    <div class="card"><h2>限时调试会话</h2>
      <div class="mut" style="margin-bottom:8px">
        为远程排障开放一支临时令牌：有效期、可访问目录与命令均可限定；令牌仅显示一次，服务端只存哈希。
      </div>
      <div class="row" style="flex-wrap:wrap;gap:6px">
        <input id="rdLabel" placeholder="用途备注" style="width:160px">
        <select id="rdTtl">
          <option value="900">15 分钟</option>
          <option value="3600" selected>1 小时</option>
          <option value="14400">4 小时</option>
          <option value="28800">8 小时（上限）</option>
        </select>
        <input id="rdRoots" placeholder="限定目录（留空=默认）" style="width:230px">
        <input id="rdCmds" placeholder="限定命令（留空=全部只读）" style="width:200px">
        <button onclick="${P}openSession()">开放会话</button>
        <button class="ghost danger" onclick="${P}revokeAll()">全部吊销</button>
      </div>
      <div id="rdTokenBox" style="margin-top:8px"></div>
      <table style="margin-top:10px"><thead><tr>
        <th>用途</th><th>会话</th><th>剩余</th><th>目录</th><th>命令</th><th>调用</th><th></th>
      </tr></thead><tbody>${sessRows}</tbody></table>
    </div>

    <div class="card"><h2>调用审计</h2>
      <div id="rdAuditBox"><button class="ghost" onclick="${P}loadAudit()">加载最近记录</button></div>
    </div>`;
  }

  function fill(text) {
    const el = document.getElementById('rdCmd');
    if (!el) return;
    el.value = el.value ? el.value.replace(/\n?$/, '\n' + text) : text;
    el.focus();
  }

  function clearOut() {
    const el = document.getElementById('rdOut');
    if (el) el.textContent = '（输出将显示在此）';
  }

  async function runExec() {
    const el = document.getElementById('rdCmd');
    const out = document.getElementById('rdOut');
    if (!el || !out) return;
    const command = el.value.trim();
    if (!command) { out.textContent = '请先输入命令'; return; }
    out.textContent = '执行中...';
    try {
      const r = await api('POST', '/api/remotedebug/exec', { command });
      out.textContent = renderResult(r);
    } catch (e) {
      out.textContent = '执行失败：' + ((e && e.message) || e);
    }
  }

  function renderResult(r) {
    const parts = [];
    const steps = r.steps || [];
    if (steps.length > 1) {
      steps.forEach((s, i) => {
        parts.push('$ ' + (s.argv || []).join(' ') + (s.ok ? '' : '  [退出码 ' + s.exit_code + ']'));
        if (s.stdout) parts.push(s.stdout.replace(/\n$/, ''));
        if (s.stderr) parts.push('[stderr] ' + s.stderr.replace(/\n$/, ''));
        if (i < steps.length - 1) parts.push('');
      });
    } else {
      if (r.argv) parts.push('$ ' + r.argv.join(' '));
      if (r.stdout) parts.push(r.stdout.replace(/\n$/, ''));
      if (r.stderr) parts.push('[stderr] ' + r.stderr.replace(/\n$/, ''));
    }
    const flags = [];
    if (r.redactions) flags.push('已脱敏 ' + r.redactions + ' 处');
    if (r.truncated) flags.push('输出已截断');
    if (r.duration_ms !== undefined) flags.push(r.duration_ms + 'ms');
    if (flags.length) parts.push('\n[' + flags.join(' · ') + ']');
    return parts.join('\n') || '（无输出）';
  }

  async function openSession() {
    const box = document.getElementById('rdTokenBox');
    const label = (document.getElementById('rdLabel') || {}).value || '调试会话';
    const ttl = parseInt((document.getElementById('rdTtl') || {}).value) || 3600;
    const rootsRaw = ((document.getElementById('rdRoots') || {}).value || '').trim();
    const cmdsRaw = ((document.getElementById('rdCmds') || {}).value || '').trim();
    const body = { label, ttl_seconds: ttl };
    if (rootsRaw) body.roots = rootsRaw.split(/[\s,]+/).filter(Boolean);
    if (cmdsRaw) body.commands = cmdsRaw.split(/[\s,]+/).filter(Boolean);
    if (box) box.innerHTML = '<span class="mut">创建中...</span>';
    try {
      const r = await api('POST', '/api/remotedebug/sessions', body);
      const usage = `curl -sS -X POST '<面板地址>/api/remotedebug/exec' `
        + `-H 'Content-Type: application/json' `
        + `-d '{"token":"${r.token}","command":"ls -l ${(r.session.roots || ['/opt/aups'])[0]}"}'`;
      if (box) {
        box.innerHTML = `<div class="ok" style="margin-bottom:4px">令牌仅显示一次，请立即复制：</div>
          <pre style="white-space:pre-wrap;word-break:break-all;background:rgba(0,0,0,.18);padding:8px;border-radius:6px;font-size:12px">${esc(r.token)}</pre>
          <div class="row" style="margin-top:6px;flex-wrap:wrap">
            <button class="ghost" onclick="${P}copy('${esc(r.token)}')">复制令牌</button>
            <button class="ghost" onclick="${P}copyUsage(${JSON.stringify(usage).replace(/</g, '\\u003c')})">复制 curl 示例</button>
          </div>`;
      }
      await terminal();
    } catch (e) {
      if (box) box.innerHTML = '<span class="bad">创建失败：' + esc((e && e.message) || e) + '</span>';
    }
  }

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => alert('已复制'))
        .catch(() => alert(text));
    } else { alert(text); }
  }

  function copyUsage(text) { copy(text); }

  async function revoke(sid) {
    if (!confirm('吊销该调试会话？吊销后令牌立即失效。')) return;
    try { await api('POST', '/api/remotedebug/sessions/' + encodeURIComponent(sid) + '/revoke'); await terminal(); }
    catch (e) { alert('吊销失败：' + ((e && e.message) || e)); }
  }

  async function revokeAll() {
    if (!confirm('吊销全部调试会话？')) return;
    try { const r = await api('POST', '/api/remotedebug/revoke-all'); alert('已吊销 ' + (r.revoked || 0) + ' 个会话'); await terminal(); }
    catch (e) { alert('操作失败：' + ((e && e.message) || e)); }
  }

  async function loadAudit() {
    const box = document.getElementById('rdAuditBox');
    if (!box) return;
    box.innerHTML = '<span class="mut">加载中...</span>';
    try {
      const r = await api('GET', '/api/remotedebug/audit?limit=100');
      const rows = (r.audit || []).map(a => `<tr>
        <td class="mut" style="font-size:11px">${esc(fmtTs(a.ts))}</td>
        <td class="mut" style="font-size:11px">${esc(a.ip || '')}</td>
        <td class="mut" style="font-size:11px">${esc(a.label || '')}</td>
        <td style="font-family:ui-monospace,monospace;font-size:11px;word-break:break-all">${esc(a.command || '')}</td>
        <td>${a.ok ? '<span class="ok">通过</span>' : '<span class="bad">失败</span>'}</td>
        <td class="mut" style="font-size:11px">${esc(String(a.redactions == null ? '-' : a.redactions))}</td>
      </tr>`).join('');
      box.innerHTML = `<table><thead><tr><th>时间</th><th>来源</th><th>用途</th>
        <th>命令</th><th>结果</th><th>脱敏</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="6" class="mut">暂无记录</td></tr>'}</tbody></table>`;
    } catch (e) {
      box.innerHTML = '<span class="bad">加载失败：' + esc((e && e.message) || e) + '</span>';
    }
  }

  return {
    title: '远程调试',
    sections: [
      { id: 'terminal', title: '终端命令' },
    ],
    go: terminal,
    open: function (s) { terminal(); },
    terminal, fill, clearOut, runExec, openSession, copy, copyUsage,
    revoke, revokeAll, loadAudit,
  };
})();
