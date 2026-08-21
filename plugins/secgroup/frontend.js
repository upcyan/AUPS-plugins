/* AUPS 插件：原生安全组（nftables provider + 黑名单订阅）。 */
window.AUPS_PLUGINS=window.AUPS_PLUGINS||{};
window.AUPS_PLUGINS.secgroup=(function(){
  const P='AUPS_PLUGINS.secgroup.';
  let cache=[], cronState={enabled:false,check_minutes:5};
  function root(){return document.getElementById('view');}
  function time(v){return v?new Date(v*1000).toLocaleString():'从未';}
  function nav(active){return `<div class="row" style="margin-bottom:12px;flex-wrap:wrap"><button class="${active==='overview'?'':'ghost'}" onclick="${P}open('overview')">安全组规则</button><button class="${active==='blacklists'?'':'ghost'}" onclick="${P}open('blacklists')">黑名单订阅</button></div>`;}
  async function overview(){
    const el=root(); if(!el)return;
    el.innerHTML=nav('overview')+'<div class="card"><span class="spinner"></span> 加载安全组状态...</div>';
    try{
      const st=await api('GET','/api/secgroup/status');
      const rows=(st.rules||[]).map(r=>`<tr><td>${esc(r.action||'-')}</td><td>${esc(r.protocol||'-')}</td><td>${esc(r.port||'-')}</td><td>${esc(r.source||'-')}</td></tr>`).join('')||'<tr><td colspan="4" class="mut">暂无托管关闭规则</td></tr>';
      el.innerHTML=nav('overview')+`<div class="card"><h2>原生安全组</h2><div class="row" style="gap:18px;flex-wrap:wrap"><div><span class="mut">nftables</span> ${st.installed?'<span class="ok">可用</span>':'<span class="bad">未安装</span>'}</div><div><span class="mut">模式</span> ${esc(st.mode||'-')}</div><div><span class="mut">规则</span> ${(st.rules||[]).length}</div><div><span class="mut">订阅黑名单</span> ${st.blacklist_count||0} 个网段</div></div><div class="mut" style="margin-top:10px">仅维护 inet aups_secgroup 专用表，不清空系统规则。</div><div class="row" style="margin-top:10px"><button onclick="show('security')">进入安全组</button><button class="ghost" onclick="${P}open('blacklists')">管理黑名单</button><button class="ghost" onclick="${P}overview()">刷新</button></div></div><div class="card"><h2>托管规则</h2><div style="overflow:auto"><table><tr><th>动作</th><th>协议</th><th>端口</th><th>来源</th></tr>${rows}</table></div></div>`;
    }catch(e){el.innerHTML=nav('overview')+'<div class="card"><span class="bad">加载失败：'+esc((e&&e.message)||e)+'</span></div>';}
  }
  async function blacklists(){
    const el=root(); if(!el)return;
    el.innerHTML=nav('blacklists')+'<div class="card"><span class="spinner"></span> 加载订阅...</div>';
    try{
      const st=await api('GET','/api/secgroup/blacklists'); cache=st.subscriptions||[]; cronState=st.schedule||cronState;
      const rows=cache.map(s=>`<tr><td><b>${esc(s.name||s.url)}</b><div class="mut" style="font-size:12px;word-break:break-all">${esc(s.url)}</div></td><td>${esc(s.provider||'generic')}<div class="mut">${s.enabled?'已启用':'已停用'} · ${s.has_token?'已认证':'无认证'}</div></td><td>${s.count||0}</td><td>${esc(time(s.last_fetch))}${s.last_error?`<div class="bad" style="max-width:260px">${esc(s.last_error)}</div>`:''}</td><td><div class="row" style="flex-wrap:wrap"><button class="ghost" data-fx-persist="true" onclick="${P}syncOne('${s.id}',this)">更新</button><button class="ghost" onclick="${P}edit('${s.id}')">编辑</button><button class="ghost" data-fx-persist="true" onclick="${P}remove('${s.id}',this)">删除</button></div></td></tr>`).join('');
      const sc=st.schedule||{};
      el.innerHTML=nav('blacklists')+`<div class="card"><h2>远程黑名单</h2><div class="row" style="gap:18px;flex-wrap:wrap"><div><span class="mut">订阅</span> ${st.subscription_count||0}</div><div><span class="mut">生效网段</span> ${st.network_count||0}</div><div><span class="mut">定时更新</span> ${sc.enabled?`<span class="ok">每 ${sc.check_minutes} 分钟检查</span>`:'未启用'}</div></div><div class="mut" style="margin-top:10px">兼容长亭 SafeLine、CrowdSec Blocklist Mirror / LAPI Decisions，以及通用 IP/CIDR 文本或 JSON。同步失败会保留上次成功规则。</div><div class="row" style="margin-top:10px;flex-wrap:wrap"><button onclick="${P}edit('')">添加订阅</button><button class="ghost" data-fx-persist="true" onclick="${P}syncAll(this)">全部更新</button><button class="ghost" onclick="${P}schedule()">定时更新设置</button></div></div><div id="sgEditor"></div><div class="card"><h2>订阅列表</h2><div style="overflow:auto"><table><tr><th>名称 / 地址</th><th>来源</th><th>网段</th><th>上次更新</th><th>操作</th></tr>${rows||'<tr><td colspan="5" class="mut">暂无订阅，请点击“添加订阅”</td></tr>'}</table></div></div>`;
    }catch(e){el.innerHTML=nav('blacklists')+'<div class="card"><span class="bad">加载失败：'+esc((e&&e.message)||e)+'</span></div>';}
  }
  function edit(id){
    const s=cache.find(x=>x.id===id)||{}; const box=document.getElementById('sgEditor'); if(!box)return;
    box.innerHTML=`<div class="card"><h2>${id?'编辑':'添加'}黑名单订阅</h2><div class="row" style="align-items:end;flex-wrap:wrap"><label class="blk" style="flex:1;min-width:180px"><span class="mut">名称</span><input id="sgName" value="${esc(s.name||'')}" placeholder="如 CrowdSec 社区黑名单" style="width:100%"></label><label class="blk"><span class="mut">来源类型</span><select id="sgProvider"><option value="chaitin">长亭 SafeLine</option><option value="crowdsec">CrowdSec</option><option value="generic">通用</option></select></label></div><label class="blk"><span class="mut">订阅 URL</span><input id="sgUrl" value="${esc(s.url||'')}" placeholder="https://..." style="width:100%"></label><div class="row" style="align-items:end;flex-wrap:wrap"><label class="blk"><span class="mut">认证方式</span><select id="sgAuth"><option value="none">无</option><option value="bearer">Bearer Token</option><option value="x-api-key">X-Api-Key</option><option value="basic">Basic（用户:密码）</option></select></label><label class="blk" style="flex:1;min-width:180px"><span class="mut">密钥${s.has_token?'（留空保持原值）':''}</span><input id="sgToken" type="password" placeholder="${s.has_token?'已配置':'可选'}" style="width:100%"></label><label class="blk"><span class="mut">更新周期（分钟）</span><input id="sgInterval" type="number" min="1" value="${Math.max(1,Math.round((s.interval_sec||3600)/60))}" style="width:120px"></label></div><div class="row" style="margin-top:10px"><label><input id="sgEnabled" type="checkbox" ${s.enabled===false?'':'checked'}> 启用</label><label><input id="sgNow" type="checkbox" ${id?'':'checked'}> 保存后立即同步</label></div><div class="row" style="margin-top:10px"><button data-fx-persist="true" onclick="${P}save(this)">保存</button><button class="ghost" onclick="document.getElementById('sgEditor').innerHTML=''">取消</button></div></div>`;
    document.getElementById('sgProvider').value=s.provider||'crowdsec'; document.getElementById('sgAuth').value=s.auth_type||'none';
  }
  async function save(btn){
    const done=beginButtonTask(btn); try{
      const body={name:document.getElementById('sgName').value.trim(),provider:document.getElementById('sgProvider').value,url:document.getElementById('sgUrl').value.trim(),auth_type:document.getElementById('sgAuth').value,interval_sec:Number(document.getElementById('sgInterval').value)*60,enabled:document.getElementById('sgEnabled').checked,sync_now:document.getElementById('sgNow').checked};
      const token=document.getElementById('sgToken').value; if(token)body.token=token;
      await api('POST','/api/secgroup/blacklists',body); await blacklists();
    }catch(e){alert('保存失败：'+((e&&e.message)||e));}finally{done();}
  }
  async function syncOne(id,btn){const done=beginButtonTask(btn);try{await api('POST','/api/secgroup/blacklists/sync',{id});await blacklists();}catch(e){alert('更新失败：'+((e&&e.message)||e));}finally{done();}}
  async function syncAll(btn){const done=beginButtonTask(btn);try{await api('POST','/api/secgroup/blacklists/sync',{});await blacklists();}catch(e){alert('更新失败：'+((e&&e.message)||e));}finally{done();}}
  async function remove(id,btn){if(!confirm('删除此订阅并撤销其黑名单规则？'))return;const done=beginButtonTask(btn);try{await api('DELETE','/api/secgroup/blacklists/'+encodeURIComponent(id));await blacklists();}catch(e){alert('删除失败：'+((e&&e.message)||e));}finally{done();}}
  function schedule(){const box=document.getElementById('sgEditor');if(!box)return;box.innerHTML=`<div class="card"><h2>定时更新设置</h2><div class="row" style="align-items:end;flex-wrap:wrap"><label><input id="sgCronOn" type="checkbox" ${cronState.enabled?'checked':''}> 启用定时检查</label><label class="blk"><span class="mut">检查频率</span><select id="sgCronMin"><option>5</option><option>10</option><option>15</option><option>30</option><option>60</option><option>1</option></select></label><button data-fx-persist="true" onclick="${P}saveSchedule(this)">保存</button></div><div class="mut" style="margin-top:8px">定时任务只更新已达到各自更新周期的订阅。</div></div>`;document.getElementById('sgCronMin').value=String(cronState.check_minutes||5);}
  async function saveSchedule(btn){const done=beginButtonTask(btn);try{await api('POST','/api/secgroup/blacklists/schedule',{enabled:document.getElementById('sgCronOn').checked,check_minutes:Number(document.getElementById('sgCronMin').value)});await blacklists();}catch(e){alert('设置失败：'+((e&&e.message)||e));}finally{done();}}
  function open(section){return section==='blacklists'?blacklists():overview();}
  return {title:'原生安全组',sections:[{id:'overview',title:'安全组规则'},{id:'blacklists',title:'黑名单订阅'}],go:open,open,overview,blacklists,edit,save,syncOne,syncAll,remove,schedule,saveSchedule};
})();
