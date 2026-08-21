/* AUPS 插件：原生安全组（nftables provider）。 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS.secgroup = (function(){
  const P='AUPS_PLUGINS.secgroup.';
  function root(){return document.getElementById('view');}
  async function overview(){
    const el=root(); if(!el)return;
    el.innerHTML='<div class="card"><span class="spinner"></span> 加载安全组状态...</div>';
    try{
      const st=await api('GET','/api/secgroup/status');
      const rows=(st.rules||[]).map(r=>`<tr><td>${esc(r.action||'-')}</td><td>${esc(r.protocol||'-')}</td>
        <td>${esc(r.port||'-')}</td><td>${esc(r.source||'-')}</td></tr>`).join('')||'<tr><td colspan="4" class="mut">暂无托管关闭规则</td></tr>';
      el.innerHTML=`<div class="card"><h2>原生安全组</h2>
        <div class="row" style="gap:18px"><div><span class="mut">nftables</span> ${st.installed?'<span class="ok">可用</span>':'<span class="bad">未安装</span>'}</div>
          <div><span class="mut">运行模式</span> ${esc(st.mode||'-')}</div><div><span class="mut">持久化</span> ${st.persistent?'<span class="ok">已启用</span>':'-'}</div><div><span class="mut">规则</span> ${(st.rules||[]).length}</div></div>
        <div class="mut" style="margin-top:10px">仅维护 inet aups_secgroup 专用链，不清空系统规则。请在“安全加固 → 安全组”统一管理端口、协议和来源网段。</div>
        <div class="row" style="margin-top:10px"><button onclick="show('security')">进入安全组</button><button class="ghost" onclick="${P}overview()">刷新</button></div>
      </div><div class="card"><h2>托管规则</h2><div style="overflow:auto"><table><tr><th>动作</th><th>协议</th><th>端口</th><th>来源</th></tr>${rows}</table></div></div>`;
    }catch(e){el.innerHTML='<div class="card"><span class="bad">加载失败：'+esc((e&&e.message)||e)+'</span></div>';}
  }
  return {title:'原生安全组',sections:[{id:'overview',title:'安全组规则'}],go:overview,open:overview,overview};
})();
