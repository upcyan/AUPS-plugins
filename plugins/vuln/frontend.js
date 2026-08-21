/* AUPS 插件：系统补丁与部署软件版本风险检测。 */
window.AUPS_PLUGINS = window.AUPS_PLUGINS || {};
window.AUPS_PLUGINS.vuln = (function () {
  const P = 'AUPS_PLUGINS.vuln.';
  let lastResult = null;
  function rootEl(){ return document.getElementById('view'); }
  function errorHtml(e){ return `<div class="card"><h2>加载失败</h2><pre style="white-space:pre-wrap">${esc((e&&e.message)||e||'未知错误')}</pre></div>`; }
  function stateHtml(value, critical){
    if (value == null) return '<span class="mut">无法判定</span>';
    if (value) return '<span class="ok">正常</span>';
    return `<span class="bad">${critical?'存在风险':'需关注'}</span>`;
  }

  async function overview(){
    const root=rootEl(); if(!root)return;
    root.innerHTML='<div class="card" style="text-align:center;color:var(--mut)"><span class="spinner"></span> 加载中...</div>';
    try{
      const [st,rd]=await Promise.all([api('GET','/api/vuln/status'),api('GET','/api/vuln/reports').catch(()=>({reports:[]}))]);
      const ready=!!(st.linux&&st.pm);
      root.innerHTML=`<div class="card"><h2>漏洞与版本风险检测</h2>
        <div class="row" style="gap:18px;align-items:flex-start">
          <div><div class="mut">运行环境</div><div>${st.linux?'<span class="ok">Linux</span>':'<span class="bad">非 Linux</span>'}</div></div>
          <div><div class="mut">包管理器</div><div>${esc(st.pm||'未检测到')}</div></div>
          <div><div class="mut">监控软件</div><div>${st.software_count||0} 项</div></div>
          <div><div class="mut">历史报告</div><div>${(rd.reports||[]).length}</div></div>
        </div>
        <div class="mut" style="margin-top:10px">检测系统安全补丁、待更新软件、重启状态和自动安全更新。软件版本比对用于发现更新风险，不等同于完整 CVE 扫描。</div>
        <div class="row" style="margin-top:12px">
          <button onclick="${P}run()" ${ready?'':'disabled'}>运行检测</button>
          <button class="ghost" onclick="${P}fixAll()" ${ready?'':'disabled'}>安装安全补丁</button>
          <button class="ghost" onclick="${P}reports()">历史报告</button>
        </div><div id="vulnOvBox" style="margin-top:12px"></div>
      </div>`;
    }catch(e){root.innerHTML=errorHtml(e);}
  }

  async function run(){
    const box=document.getElementById('vulnOvBox'); if(!box)return;
    box.innerHTML='<div class="mut"><span class="spinner"></span> 正在查询软件源与已安装版本，可能耗时 1–2 分钟...</div>';
    try{const r=await api('POST','/api/vuln/check'); renderResult(box,r);}
    catch(e){box.innerHTML='<span class="bad">检测失败：'+esc((e&&e.message)||e)+'</span>';}
  }

  function renderResult(box,r){
    lastResult=r;
    const checks=r.checks||[],groups={};
    checks.forEach(c=>{(groups[c.group||'其他']=groups[c.group||'其他']||[]).push(c);});
    const groupsHtml=Object.entries(groups).map(([name,list])=>{
      const bad=list.filter(c=>c.ok===false).length,unknown=list.filter(c=>c.ok==null).length;
      const rows=list.map(c=>{
        const id=encodeURIComponent(c.id||'').replace(/'/g,'%27');
        const fix=c.ok===false&&c.fixable?`<button class="ghost" onclick="${P}fixOne('${id}')">修复</button>`:'';
        return `<tr><td><b>${esc(c.title||'')}</b>
            <details><summary class="mut" style="cursor:pointer">期望与建议</summary>
              <div class="mut" style="white-space:normal">期望：${esc(c.expected||'-')}<br>建议：${esc(c.advice||'-')}</div></details></td>
          <td>${stateHtml(c.ok,c.critical)}</td><td class="mut" style="white-space:normal;min-width:160px">${esc(c.current||'-')}</td><td>${fix}</td></tr>`;
      }).join('');
      return `<div class="card" style="margin-top:12px"><h2>${esc(name)} · 风险 ${bad} / 未知 ${unknown}</h2>
        <div style="overflow-x:auto"><table><thead><tr><th>检测项</th><th>状态</th><th>当前</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
    }).join('');
    box.innerHTML=`<div class="row" style="gap:12px">
      <div class="card" style="margin:0;padding:10px 14px"><span class="mut">正常</span> <b class="ok">${r.ok||0}</b></div>
      <div class="card" style="margin:0;padding:10px 14px"><span class="mut">风险</span> <b class="bad">${r.fail||0}</b></div>
      <div class="card" style="margin:0;padding:10px 14px"><span class="mut">无法判定</span> <b>${r.skipped||0}</b></div>
      <button class="ghost" onclick="${P}opnReport('${esc(r.report_id||'')}')">查看报告</button>
    </div>${groupsHtml||'<div class="mut" style="margin-top:10px">没有可用检测项</div>'}`;
  }

  async function fixOne(encodedId){
    const id=decodeURIComponent(encodedId);
    const item=((lastResult&&lastResult.checks)||[]).find(c=>c.id===id);
    if(!item)return alert('检测结果已失效，请重新检测');
    const scope=item.fix_scope||(item.pkg?'package':'security');
    const label=scope==='all'?'升级全部待更新包':scope==='security'?'安装安全补丁':'升级 '+(item.pkg||item.title);
    if(!confirm(label+'？此操作会调用系统包管理器，可能影响运行中的服务。'))return;
    await executeFix(scope,item.pkg,label);
  }
  async function fixAll(){
    if(!confirm('安装当前系统的安全通道补丁？操作可能耗时较长，关键库更新后可能需要重启。'))return;
    await executeFix('security',null,'安装安全补丁');
  }
  async function executeFix(scope,pkg,label){
    const box=document.getElementById('vulnOvBox'); if(!box)return;
    box.innerHTML='<div class="mut"><span class="spinner"></span> 正在'+esc(label)+'...</div>';
    try{
      const r=await api('POST','/api/vuln/fix',{scope,pkg});
      if(!r.ok){box.innerHTML='<span class="bad">'+esc(r.summary||'修复失败')+'</span><pre>'+esc(r.detail||'')+'</pre>';return;}
      box.innerHTML='<span class="ok">'+esc(r.summary||'修复完成')+'</span><div class="mut">正在重新检测...</div>';
      await run();
    }catch(e){box.innerHTML='<span class="bad">修复失败：'+esc((e&&e.message)||e)+'</span>';}
  }

  async function reports(){
    const box=document.getElementById('vulnOvBox'); if(!box)return;
    box.innerHTML='<div class="mut"><span class="spinner"></span> 加载报告...</div>';
    try{
      const d=await api('GET','/api/vuln/reports');
      const rows=(d.reports||[]).map(r=>`<tr><td>${esc(r.ts||'-')}</td><td class="mut">${esc(r.summary||'-')}</td>
        <td><button class="ghost" onclick="${P}opnReport('${esc(r.id)}')">查看</button></td></tr>`).join('')||'<tr><td colspan="3" class="mut">暂无漏洞检测报告</td></tr>';
      box.innerHTML=`<div class="row" style="margin-bottom:8px"><button onclick="${P}run()">重新检测</button></div>
        <div style="overflow-x:auto"><table><thead><tr><th>时间</th><th>摘要</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }catch(e){box.innerHTML=errorHtml(e);}
  }
  async function opnReport(rid){
    try{
      if(!rid){const list=await api('GET','/api/vuln/reports');if(!(list.reports||[]).length)return alert('暂无漏洞检测报告');rid=list.reports[0].id;}
      const d=await api('GET','/api/vuln/report/'+encodeURIComponent(rid)),res=d.result||{};
      const rows=(res.checks||[]).map(c=>`<tr><td>${esc(c.title||'')}</td><td>${stateHtml(c.ok,c.critical)}</td>
        <td class="mut" style="white-space:normal">${esc(c.current||'-')}</td><td class="mut" style="white-space:normal">${esc(c.advice||'-')}</td></tr>`).join('')||'<tr><td colspan="4" class="mut">无检测项</td></tr>';
      const modal=document.createElement('div');modal.className='ov-modal';modal.innerHTML=`<div class="ov-modal-box" style="width:min(860px,94vw);max-height:82vh;overflow:auto">
        <h3>漏洞与版本风险报告</h3><div class="mut">${esc(d.ts||'')} · ${esc(res.summary||'')}</div>
        <div style="overflow-x:auto;margin-top:10px"><table><thead><tr><th>检测项</th><th>状态</th><th>当前</th><th>建议</th></tr></thead><tbody>${rows}</tbody></table></div>
        <div class="row" style="margin-top:12px"><button class="ghost" onclick="this.closest('.ov-modal').remove()">关闭</button></div></div>`;
      document.body.appendChild(modal);
    }catch(e){alert('读取报告失败：'+((e&&e.message)||e));}
  }
  return {title:'漏洞检测',sections:[{id:'overview',title:'漏洞检测'}],go:overview,open:overview,overview,run,fixOne,fixAll,reports,opnReport};
})();
