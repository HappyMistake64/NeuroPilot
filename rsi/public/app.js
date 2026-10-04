'use strict';
const $=id=>document.getElementById(id);
async function api(path,body){const r=await fetch('/rsi/api/'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||r.status);return data;}
function el(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function button(text,fn,style='secondary'){const n=el('button',text);n.className=style;n.onclick=async()=>{n.disabled=true;try{await fn();$('message').textContent='';await refresh();}catch(e){$('message').textContent=e.message;}finally{n.disabled=false;}};return n;}
function showReport(run){
 const report=run.report||run;
 $('report').textContent=JSON.stringify(run,null,2);
 let text=`Stav: ${report.status||run.status||'neznámý'}. `;
 if(report.pilot_capability_gain_confirmed)text+='Potvrzen přínos schopností v pilotu. ';
 if(report.pilot_efficiency_gain_confirmed)text+='Potvrzena úspora tokenů při stejných výsledcích. ';
 if(report.kind==='study')text+=report.audit_complete?'A/B audit dokončen; jde o jedno pilotní srovnání. ':'A/B audit není dokončen. ';
 if(report.actual_rsi_improvement_proven===false)text+='Obecný přínos RSI není prokázán.';
 $('outcome').textContent=text;
}
let polling=false;
async function refresh(){if(polling)return;polling=true;try{const data=await api('status');$('study_plan').textContent=data.study_plan?JSON.stringify(data.study_plan,null,2):'Nejdřív připrav A/B plán.';
$('limits').textContent=`Limity jedné větve: ${data.limits.max_calls} volání, ${data.limits.max_tokens} tokenů, ${data.limits.max_seconds} sekund. Brána úspory: ${data.gates.allow_efficiency?data.gates.min_token_saving_percent+' %':'vypnutá'}.`;
$('provider_status').textContent=`Aktivní připojení: ${data.provider.kind} · ${data.provider.model||'model není vybrán'}`;
$('active').textContent=data.active||'Nepřipraveno';$('job').textContent=JSON.stringify(data.job,null,2);$('benchmark').textContent=data.benchmark?`Úlohy: ${JSON.stringify(data.benchmark.counts)} · ${data.benchmark.kind}`:'Úlohy ještě nejsou připravené.';
$('versions').replaceChildren(...data.artifacts.map(a=>{const row=el('tr');for(const value of[a.id,a.parent||'—',a.status,a.hypothesis])row.append(el('td',value));const cell=el('td');cell.append(button('Zobrazit změnu',async()=>{const item=await api('artifact/'+encodeURIComponent(a.id));$('report').textContent=item.diff||'Beze změny';$('outcome').textContent=item.hypothesis;}));if(a.status==='accepted'&&a.id!==data.active)cell.append(button('Použít verzi',()=>api('job',{kind:'activate',artifact:a.id})));row.append(cell);return row;}));
$('runs').replaceChildren(...data.runs.map(r=>{const line=el('div');line.append(button(`${r.kind} · ${r.status} · ${r.id}`,async()=>{showReport(await api('run/'+encodeURIComponent(r.id)));}));if(r.status==='running')line.append(button('Zastavit',()=>api('stop/'+encodeURIComponent(r.id),{}),'danger'));return line;}));
}finally{polling=false;}}
for(const kind of['init','doctor','provider_check','baseline','campaign','rollback','study_prepare','study']){$(kind).onclick=async()=>{$(kind).disabled=true;try{if(kind==='rollback'&&!confirm('Vrátit předchozí verzi RSI agenta?'))return;await api(kind==='init'?'init':'job',kind==='init'?{}:{kind});await refresh();}catch(e){$('message').textContent=e.message;}finally{$(kind).disabled=false;}};}
refresh().catch(e=>{$('message').textContent=e.message;});setInterval(()=>refresh().catch(e=>{$('message').textContent=e.message;}),2000);

let accountSignature='',authPolling=false,authEpoch=0,lastOpenAIAccount=null;
async function refreshOpenAI(){
 if(authPolling)return;authPolling=true;
 try{
  const epoch=authEpoch;const data=await api('openai/status');if(epoch!==authEpoch)return;
  const signature=JSON.stringify(data.accounts);
  if(signature!==accountSignature){
   const previous=$('openai_account').value;
   $('openai_account').replaceChildren(new Option('Nový účet / workspace',''),...data.accounts.map(a=>new Option(`${a.email||'Účet'} · ${a.id.slice(-8)}${a.signed_in?'':' · odhlášen'}`,a.id)));
   if(data.accounts.some(a=>a.id===previous))$('openai_account').value=previous;else if(data.active)$('openai_account').value=data.active;
   accountSignature=signature;
  }
  if(lastOpenAIAccount!==data.active){$('openai_model').replaceChildren(new Option('Načti modely pro tento účet',''));lastOpenAIAccount=data.active;}
  const active=data.accounts.find(a=>a.id===data.active);
  const states={waiting:'Čekám na dokončení v prohlížeči.',connected:'Přihlášení dokončeno. Načti modely a vyber model pro RSI.',expired:'Přihlášení vypršelo. Zahaj nový pokus.',failed:'Přihlášení selhalo. Zkus to znovu a povol využití předplatného.',cancelled:'Přihlášení zrušeno.',idle:''};
  $('openai_status').textContent=(active?`Aktivní účet: ${active.email||'ChatGPT'} · ${active.id.slice(-8)}. `:'Účet není přihlášen. ')+(states[data.login.status]||'');
  $('openai_cancel').hidden=data.login.status!=='waiting';
  if(data.login.status!=='waiting'){$('openai_link').hidden=true;$('openai_link').removeAttribute('href');}
 }finally{authPolling=false;}
}
function authButton(id,fn){$(id).onclick=async()=>{authEpoch++;$(id).disabled=true;try{$('message').textContent='';await fn();await refreshOpenAI();await refresh();}catch(e){$('message').textContent=e.message;}finally{$(id).disabled=false;}};}
authButton('openai_login',async()=>{
 const result=await api('openai/login',{account:$('openai_account').value||null});
 const url=new URL(result.url);if(url.origin!=='https://auth.openai.com')throw Error('Neplatná přihlašovací adresa.');
 $('openai_link').href=url.href;$('openai_link').hidden=false;$('openai_link').focus();
});
authButton('openai_cancel',()=>api('openai/cancel',{}));
authButton('openai_select',async()=>{await api('openai/select',{account:$('openai_account').value});$('openai_model').replaceChildren(new Option('Načti modely pro tento účet',''));});
authButton('openai_logout',async()=>{const result=await api('openai/logout',{});$('message').textContent=result.message;$('openai_model').replaceChildren(new Option('Nejdřív se přihlas',''));});
authButton('openai_models',async()=>{const data=await api('openai/models',{});$('openai_model').replaceChildren(new Option('Vyber model',''),...data.models.map(m=>new Option(m.name,m.id)));});
authButton('openai_save',()=>api('openai/configure',{model:$('openai_model').value}));
authButton('use_ollama',()=>api('openai/ollama',{}));
refreshOpenAI().catch(e=>{$('openai_status').textContent=e.message;});
setInterval(()=>refreshOpenAI().catch(e=>{$('openai_status').textContent=e.message;}),3000);

for(const id of ['codex_models','codex_save'])$(id).onclick=async()=>{
 $(id).disabled=true;
 try{
  $('message').textContent='';
  if(id==='codex_models'){
   const data=await api('codex/status',{});
   $('codex_model').replaceChildren(new Option('Vyber model',''),...(data.models||[]).map(m=>new Option(m.id,m.id)));
   $('codex_status').textContent=data.signed_in?'ChatGPT je přihlášený. Vyber model, použij ho pro RSI a spusť test spojení.':'Nejdřív spusť codex-login v terminálu.';
  }else{
   await api('codex/configure',{model:$('codex_model').value});
   $('codex_status').textContent='Codex je vybraný pro RSI. Skutečnou odpověď ověř tlačítkem Otestovat spojení.';
   await refresh();
  }
 }catch(e){$('message').textContent=e.message;}finally{$(id).disabled=false;}
};
