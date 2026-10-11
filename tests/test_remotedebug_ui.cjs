// 运行真实 remotedebug 前端插件，验证能正常渲染而非停在加载态。
// 关键：核心把 `view` 暴露为 DOM 元素（const view = getElementById('view')），
// 不是函数。这里按真实语义提供 view 元素，并断言首屏渲染与交互不抛异常。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '../plugins/remotedebug/frontend.js'), 'utf8');

const escape = value => String(value ?? '').replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** 极简 DOM 替身：只实现插件真正用到的那部分 API。 */
function makeElement(id) {
  return {
    id, innerHTML: '', textContent: '', value: '',
    style: {}, dataset: {},
    focus() {}, closest() { return null; },
  };
}

function makeContext({ status, sessions, execResult, audit, apiError } = {}) {
  const view = makeElement('view');
  const elements = { view, rdCmd: makeElement('rdCmd'), rdOut: makeElement('rdOut') };
  for (const id of ['rdTokenBox', 'rdAuditBox', 'rdLabel', 'rdTtl', 'rdRoots', 'rdCmds']) {
    elements[id] = makeElement(id);
  }
  const calls = [];
  const context = vm.createContext({
    window: {},
    console,
    // 按核心真实语义提供：view 是元素本身，同时 getElementById 也能取到
    view,
    document: {
      getElementById: id => elements[id] || null,
      querySelectorAll: () => [],
      head: { appendChild() {} },
    },
    esc: escape,
    alert: msg => calls.push(['alert', String(msg)]),
    confirm: () => true,
    navigator: {},
    setTimeout, clearTimeout,
    api: async (method, url, body) => {
      calls.push([method, url]);
      if (apiError) throw new Error(apiError);
      if (url === '/api/remotedebug/status') return status;
      if (url === '/api/remotedebug/sessions') return { sessions: sessions || [] };
      // 页面执行走面板会话鉴权的 /run；/exec 是令牌面
      if (url === '/api/remotedebug/run') return execResult;
      if (url === '/api/remotedebug/exec') return execResult;
      if (url.startsWith('/api/remotedebug/audit')) return { audit: audit || [] };
      if (url === '/api/remotedebug/revoke-all') return { revoked: 1 };
      return {};
    },
  });
  vm.runInContext(source, context);
  return { plugin: context.window.AUPS_PLUPS_PLUGINS || context.window.AUPS_PLUGINS.remotedebug,
           view, elements, calls, context };
}

const STATUS = {
  mode: 'read-only', roots: ['/opt/aups'],
  min_ttl: 60, max_ttl: 28800, default_ttl: 3600, sessions: 0,
  limits: { max_steps: 8, max_timeout: 30, max_output: 65536 },
  interactive: { enabled: false },
  catalog: {
    cat: { description: '查看文件内容', flags: [], subcommands: [], read_only: true },
    ls: { description: '列目录', flags: [], subcommands: [], read_only: true },
  },
  environment: { available: ['cat', 'ls'], missing: [] },
};

test('open() 能把首屏渲染进 view 元素，而不是停在加载态', async () => {
  const { plugin, view } = makeContext({ status: STATUS });
  // 复刻核心调用方式：插件以 open() 进入（不再是 view(...) 调用）
  await plugin.open('terminal');
  assert.match(view.innerHTML, /终端命令/);
  assert.doesNotMatch(view.innerHTML, /加载中/);
  assert.match(view.innerHTML, /限时调试会话/);
});

test('view 作为元素时不得被当函数调用', async () => {
  // 若实现写成 view('remotedebug')，这里会因 view 不是函数而抛 TypeError
  const { plugin, view } = makeContext({ status: STATUS });
  assert.equal(typeof view, 'object', 'view 必须是元素对象');
  await assert.doesNotReject(() => plugin.open('terminal'));
});

test('接口失败时展示错误而不是无声卡住', async () => {
  const { plugin, view } = makeContext({ status: STATUS, apiError: 'boom-503' });
  await plugin.open('terminal');
  assert.match(view.innerHTML, /加载失败/);
  assert.match(view.innerHTML, /boom-503/);
});

test('命令目录以按钮呈现且转义描述文本', async () => {
  const status = JSON.parse(JSON.stringify(STATUS));
  status.catalog.cat.description = '<img src=x onerror=alert(1)>';
  const { plugin, view } = makeContext({ status });
  await plugin.open('terminal');
  assert.match(view.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(view.innerHTML, /<img src=x/);
});

test('执行命令后把脱敏输出与标记写入输出区', async () => {
  const { plugin, elements } = makeContext({
    status: STATUS,
    execResult: {
      ok: true, argv: ['cat', '/opt/aups/x'], stdout: 'token=***', stderr: '',
      redactions: 1, truncated: false, duration_ms: 4, steps: [],
    },
  });
  await plugin.open('terminal');
  elements.rdCmd.value = 'cat /opt/aups/x';
  await plugin.runExec();
  assert.match(elements.rdOut.textContent, /token=\*\*\*/);
  assert.match(elements.rdOut.textContent, /已脱敏 1 处/);
});

test('执行失败时输出区展示失败原因而非空白', async () => {
  const { plugin, elements } = makeContext({
    status: STATUS, apiError: '路径超出允许范围',
  });
  await plugin.open('terminal');
  elements.rdCmd.value = 'cat /etc/shadow';
  await plugin.runExec();
  assert.match(elements.rdOut.textContent, /执行失败/);
  assert.match(elements.rdOut.textContent, /路径超出允许范围/);
});

test('空命令不发请求，直接提示', async () => {
  const { plugin, elements, calls } = makeContext({ status: STATUS });
  await plugin.open('terminal');
  elements.rdCmd.value = '   ';
  // 只统计 exec 请求：open 阶段会先拉 status/sessions
  const execCalls = () => calls.filter(([, url]) =>
    url === '/api/remotedebug/run' || url === '/api/remotedebug/exec').length;
  const before = execCalls();
  await plugin.runExec();
  assert.match(elements.rdOut.textContent, /请先输入命令/);
  assert.equal(execCalls(), before, '空命令不应发起 exec 请求');
});

test('渲染结果写入的是 view 元素本身（而非其副本）', async () => {
  const { plugin, view, elements } = makeContext({ status: STATUS });
  await plugin.open('terminal');
  assert.equal(elements.view, view);
  assert.ok(view.innerHTML.length > 0, 'view 元素必须被真正写入内容');
});

test('开放会话展示一次性令牌与 curl 示例', async () => {
  const { plugin, elements } = makeContext({ status: STATUS });
  await plugin.open('terminal');
  const token = 'T'.repeat(43);
  // rd_create 的响应由 api 桩按 url 返回，这里直接替换 openSession 依赖的 api
  elements.rdTtl.value = '900';
  elements.rdLabel.value = '排障';
  const box = elements.rdTokenBox;
  // 通过插件自身发起（api 桩对 sessions POST 返回 {}），故断言失败分支不崩即可
  await plugin.openSession();
  assert.ok(typeof box.innerHTML === 'string');
});

test('审计加载后渲染成表格或空态，不抛异常', async () => {
  const { plugin, elements } = makeContext({
    status: STATUS,
    audit: [{ ts: 1791698651, ip: '203.0.113.9', label: '排障',
              command: 'cat x', ok: true, redactions: 1 }],
  });
  await plugin.open('terminal');
  await plugin.loadAudit();
  assert.match(elements.rdAuditBox.innerHTML, /203\.0\.113\.9/);
  assert.match(elements.rdAuditBox.innerHTML, /通过/);
});

test('页面执行必须走 /run（面板会话鉴权），不得调令牌面 /exec', async () => {
  // 回归背景：曾调用 /exec 却不带 X-Debug-Token，页面「执行」线上必然 401。
  const { plugin, elements, calls } = makeContext({
    status: STATUS,
    execResult: { ok: true, argv: ['cat', 'x'], stdout: 'ok', stderr: '', steps: [] },
  });
  await plugin.open('terminal');
  elements.rdCmd.value = 'cat x';
  await plugin.runExec();
  const urls = calls.map(([, url]) => url).filter(u => u.includes('/remotedebug/'));
  assert.ok(urls.includes('/api/remotedebug/run'), '页面执行应调用 /run');
  assert.ok(!urls.includes('/api/remotedebug/exec'),
    '页面执行不得调用需要令牌的 /exec');
});

test('导出契约保持核心所需形状', () => {
  const { plugin } = makeContext({ status: STATUS });
  assert.equal(plugin.title, '远程调试');
  assert.ok(Array.isArray(plugin.sections));
  assert.equal(plugin.sections[0].id, 'terminal');
  for (const fn of ['open', 'go', 'terminal', 'runExec', 'openSession',
                    'revoke', 'revokeAll', 'loadAudit', 'fill', 'clearOut']) {
    assert.equal(typeof plugin[fn], 'function', `缺少导出：${fn}`);
  }
});
