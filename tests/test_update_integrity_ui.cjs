// 运行真实 appupdate 前端插件，验证版本页状态展示与转义，不启动浏览器或服务。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../plugins/appupdate/frontend.js'), 'utf8');
const escape = value => String(value ?? '').replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function render(integrity) {
  const box = { innerHTML: '' };
  const calls = [];
  const context = vm.createContext({
    window: {},
    document: { getElementById: id => {
      assert.equal(id, 'verListBox');
      return box;
    } },
    esc: escape,
    api: async (method, url) => {
      calls.push([method, url]);
      assert.equal(method, 'GET', '读取校验状态不得修改元数据');
      if (url === '/api/apps/demo/versions') {
        return { latest: { version: '1.0' }, versions: [], integrity };
      }
      assert.equal(url, '/api/apps/demo');
      return { locked: [] };
    },
  });
  vm.runInContext(source, context);
  await context.window.AUPS_PLUGINS.appupdate.loadVersions('demo');
  assert.equal(calls.length, 2);
  return box.innerHTML;
}

test('双校验通过时展示真实目标与摘要，而非 latest 的文件', async () => {
  const html = await render({ status: 'verified', file: 'apk/demo-1.0.apk',
    apkMd5: '900150983cd24fb0d6963f7d28e17f72', apkSha256: 'hash-value' });
  assert.match(html, /双校验通过/);
  assert.match(html, /apk\/demo-1.0.apk/);
  assert.match(html, /900150983cd24fb0d6963f7d28e17f72/);
  assert.match(html, /按 apkUrl，不按 latest/);
});

test('缺字段状态提示同步，不能被标成通过', async () => {
  const html = await render({ status: 'missing' });
  assert.match(html, /校验字段未补齐/);
  assert.doesNotMatch(html, /双校验通过/);
});

test('摘要不一致必须展示警告', async () => {
  const html = await render({ status: 'mismatch' });
  assert.match(html, /校验值与本地 APK 不一致/);
  assert.doesNotMatch(html, /双校验通过/);
});

test('错误文本和目标路径必须转义', async () => {
  const html = await render({ status: 'error', error: '<script>alert(1)</script>', file: '<img>' });
  assert.match(html, /无法校验/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&lt;img&gt;/);
  assert.doesNotMatch(html, /<script>|<img>/);
});

test('没有 update.json 或旧 API 无字段时保留版本页', async () => {
  const html = await render(undefined);
  assert.match(html, /未发现 update.json/);
  assert.match(html, /暂无版本/);
});
