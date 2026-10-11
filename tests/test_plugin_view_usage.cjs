// 验证 baseline / cyansecengine / yara 三个插件不再把 view 当函数调用。
//
// 回归背景：核心把 view 暴露为 DOM 元素（const view = getElementById('view')）。
// 三个插件曾写成 view('name')，抛 TypeError 后被 openPlugin 的 try/catch 吞掉，
// 页面停在「正在加载插件」占位态，用户看不到任何错误。
//
// 断言策略：view 只提供元素语义（不可调用）。若实现再次把 view 当函数，
// 这里会因 "view is not a function" 直接失败——这正是线上症状的根因。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const escape = value => String(value ?? '').replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function makeElement() {
  const el = {
    innerHTML: '', textContent: '', value: '', style: {}, dataset: {},
    lastChild: null, children: [], classList: { add() {}, remove() {}, toggle() {} },
    focus() {}, closest() { return null; },
    appendChild() {}, removeChild() {}, remove() {},
    addEventListener() {}, setAttribute() {}, getAttribute() { return null; },
  };
  el.lastChild = el;
  // 真实浏览器里 innerHTML 写入后 .card 元素即存在；替身按需返回可写元素，
  // 使 root.querySelector('.card').innerHTML = ... 这类二次渲染不因替身失真而崩。
  el.querySelector = () => makeElement();
  el.querySelectorAll = () => [];
  return el;
}

/** 载入插件前端，返回 { plugin, view, elements }。view 是纯元素、不可调用。 */
function load(plugin, apiImpl, extra = {}) {
  const source = fs.readFileSync(
    path.join(__dirname, `../plugins/${plugin}/frontend.js`), 'utf8');
  const view = makeElement();
  // 关键：view 常驻元素语义，并提供 lastChild 以支持 baseline 的二次渲染
  view.lastChild = view;
  const elements = { view };
  const errors = [];
  const context = vm.createContext({
    window: {}, console,
    view,
    document: {
      getElementById: id => elements[id] || null,
      querySelectorAll: () => [],
      head: { appendChild() {} },
      createElement: () => makeElement(),
      body: { appendChild() {} },
    },
    esc: escape,
    fmt: n => String(n),
    alert: msg => errors.push(['alert', String(msg)]),
    confirm: () => true,
    navigator: {},
    setTimeout, clearTimeout,
    api: async (method, url) => {
      if (typeof apiImpl === 'function') return apiImpl(method, url);
      return {};
    },
    ...extra,
  });
  vm.runInContext(source, context);
  return { plugin: context.window.AUPS_PLUGINS[plugin], view, elements, errors };
}

const CASES = [
  { name: 'baseline', entry: 'open', url: '/api/baseline/status',
    payload: { checks_count: 4, linux: true, reports_dir: '/opt/aups/data/hostsec' },
    marker: /基线巡检/ },
  { name: 'cyansecengine', entry: 'open', url: '/api/cyansecengine/status',
    payload: { engines: [], summary: {} }, marker: /青·擎/ },
  { name: 'yara', entry: 'open', url: '/api/yara/status',
    payload: { installed: false }, marker: /YARA|引擎/ },
];

for (const c of CASES) {
  test(`${c.name}: 首屏渲染进 view 元素，不停在加载态`, async () => {
    const { plugin, view } = load(c.name, (m, url) => {
      if (url === c.url) return c.payload;
      if (url.includes('/subscribe')) return { subscriptions: [] };
      if (url.includes('/reports')) return { reports: [] };
      return {};
    });
    assert.ok(plugin, `${c.name} 未注册`);
    assert.equal(typeof plugin[c.entry], 'function');
    await plugin[c.entry]();
    assert.ok(view.innerHTML.length > 0, 'view 必须被写入内容');
    assert.match(view.innerHTML, c.marker);
    assert.doesNotMatch(view.innerHTML, /正在加载插件|>加载中</,
      '仍停留在加载占位态 → 说明渲染函数抛错');
  });

  test(`${c.name}: view 作为元素时不得被当函数调用`, async () => {
    const { plugin, view } = load(c.name, () => ({}));
    assert.equal(typeof view, 'object', 'view 必须是元素对象');
    // 核心调用 open() 不 await、也不要求返回 Promise，故这里只要求不抛错。
    // 若实现为 view('name')，调用即抛 TypeError（线上症状的根因）。
    assert.doesNotThrow(() => plugin[c.entry](),
      'open() 同步抛错 → 仍把 view 当函数调用');
    // 让内部 await 走完，确保没有异步未捕获异常
    await new Promise(resolve => setTimeout(resolve, 0));
  });
}

test('yara: 规则订阅页同样可渲染（第二处误用）', async () => {
  const { plugin, view } = load('yara', (m, url) =>
    url.includes('/subscribe') ? { subscriptions: [] } : { installed: false });
  if (typeof plugin.go === 'function') {
    await plugin.go('rules');
  } else if (typeof plugin.rules === 'function') {
    await plugin.rules();
  }
  assert.ok(view.innerHTML.length > 0);
  assert.doesNotMatch(view.innerHTML, /正在加载插件/);
});

test('三个插件的 frontend.js 不得再出现 view("...") 调用', () => {
  for (const c of CASES) {
    const source = fs.readFileSync(
      path.join(__dirname, `../plugins/${c.name}/frontend.js`), 'utf8');
    // 去掉注释行后扫描：注释里提到该写法（说明原因）是允许的
    const code = source.split('\n')
      .filter(line => !/^\s*(\/\/|\*|\/\*)/.test(line)).join('\n');
    assert.doesNotMatch(code, /\bview\s*\(\s*['"]/,
      `${c.name}/frontend.js 仍把 view 当函数调用`);
    assert.match(code, /getElementById\(['"]view['"]\)/,
      `${c.name}/frontend.js 应使用 document.getElementById('view')`);
  }
});
