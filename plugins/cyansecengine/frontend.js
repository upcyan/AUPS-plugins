/* AUPS 插件：cyansecengine —— 青·擎（占位壳）
 * 由「插件中心」按需加载并注册到 window.AUPS_PLUGINS。
 * 依赖核心全局：api / esc / fmt / view / alert / confirm。
 *
 * v3.0.0 起为占位壳：安全能力已迁移至面板核心与 yara 依赖插件，
 * 本页仅提供迁移指引。
 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS['cyansecengine'] = (function () {
  const P = 'AUPS_PLUGINS.cyansecengine.';

  function go() {
    const root = view('cyansecengine');
    if (!root) return;
    root.innerHTML = `<div class="card" style="position:relative;z-index:1">
      <h2>青·擎</h2>
      <div class="mut" style="margin-bottom:12px">v3.0.0 起为占位壳：安全加固能力已并入面板核心与依赖插件，功能入口已迁移。</div>
      <table style="min-width:360px">
        <tr><th>能力</th><th>新位置</th></tr>
        <tr><td>主机安全（rkhunter / LMD）</td><td>面板 → 安全管理 → 主机安全</td></tr>
        <tr><td>实时防护（fanotify + WAF 联动）</td><td>面板 → 安全管理 → 实时防护</td></tr>
        <tr><td>YARA 引擎与规则订阅</td><td>插件 → YARA 引擎</td></tr>
      </table>
      <div class="mut" style="margin-top:12px">数据未迁移（按设计直接新建）：新规则目录位于 /opt/aups/data/yara/，扫描报告位于 data/hostsec/ 与 data/yara/reports/。</div>
    </div>`;
  }

  return {
    title: '青·擎',
    sections: [{id: 'migrated', title: '青·擎'}],
    go: go,
    open: go,
    migrated: go
  };
})();