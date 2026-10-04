// Real-server DOM test; does not assert model capability or graphical rendering.
const {JSDOM, VirtualConsole}=require('jsdom');
const {spawn}=require('node:child_process');
const {mkdtempSync,rmSync}=require('node:fs');
const {tmpdir}=require('node:os');
const path=require('node:path');
const net=require('node:net');
const assert=require('node:assert/strict');
async function waitFor(fn){const end=Date.now()+15000;while(Date.now()<end){if(await fn())return;await new Promise(r=>setTimeout(r,30));}throw Error('UI timeout');}
(async()=>{
 const temp=mkdtempSync(path.join(tmpdir(),'neuropilot-rsi-dom-'));
 const socket=net.createServer();await new Promise(r=>socket.listen(0,'127.0.0.1',r));const port=socket.address().port;await new Promise(r=>socket.close(r));const base=`http://127.0.0.1:${port}`;
 const child=spawn(process.env.PYTHON||'python3',['-c',`import server; server.app.run(host='127.0.0.1',port=${port},debug=False)`],{cwd:path.resolve(__dirname,'..'),env:{...process.env,NEUROPILOT_OPENAI_AUTH_DIR:path.join(temp,'auth'),NEUROPILOT_DATA:path.join(temp,'data.json'),NEUROPILOT_RSI_STATE:path.join(temp,'rsi')},stdio:'ignore'});
 let dom;
 try{
 await waitFor(async()=>{try{return(await fetch(base+'/health')).ok}catch{return false}});
 const errors=[];const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 dom=await JSDOM.fromURL(base+'/rsi',{resources:'usable',runScripts:'dangerously',virtualConsole:vc,beforeParse(w){w.fetch=(u,o)=>{
 const route=new URL(u,base).pathname;
 if(route==='/rsi/api/codex/status')return Promise.resolve({ok:true,json:async()=>({signed_in:true,model_inference_verified:false,models:[{id:'fixture-model'}]})});
 if(route==='/rsi/api/codex/configure'){
  assert.equal(JSON.parse(o.body).model,'fixture-model');
  return Promise.resolve({ok:true,json:async()=>({provider:'codex',model:'fixture-model'})});
 }
 return fetch(new URL(u,base),o);
 };w.confirm=()=>true;}});
 const $=id=>dom.window.document.getElementById(id);
 await waitFor(()=>$('init')?.onclick);$('init').click();
 await waitFor(()=>$('active').textContent.startsWith('agent-'));
 await waitFor(()=>$('openai_status').textContent.includes('Účet není přihlášen'));
 assert.match($('provider_status').textContent,/ollama/);
 $('codex_models').click();
 await waitFor(()=>$('codex_model').options.length===2);
 assert.match($('codex_status').textContent,/spusť test spojení/);
 $('codex_model').value='fixture-model';$('codex_save').click();
 await waitFor(()=>$('codex_status').textContent.includes('Skutečnou odpověď ověř'));

 $('openai_login').click();
 await waitFor(()=>!$('openai_link').hidden);
 assert.equal(new URL($('openai_link').href).origin,'https://auth.openai.com');
 assert.equal(new URL($('openai_link').href).searchParams.get('client_id'),'dynamic_agent_client');
 await waitFor(()=>!$('openai_cancel').hidden);$('openai_cancel').click();
 await waitFor(()=>$('openai_status').textContent.includes('zrušeno'));
 assert.equal($('openai_link').hidden,true);
 $('openai_models').click();
 await waitFor(()=>$('message').textContent.includes('Nejdřív se přihlas'));
 await waitFor(()=>$('active').textContent.startsWith('agent-'));
 assert.equal(dom.window.document.querySelectorAll('#versions tr').length,1);
 assert.match($('benchmark').textContent,/20/);
 dom.window.document.querySelector('#versions button').click();
 await waitFor(()=>$('report').textContent.includes('build_context'));
 $('study_prepare').click();
 await waitFor(()=>$('study_plan').textContent.includes('770'));
 assert.match($('limits').textContent,/15 %/);
 $('doctor').click();
 await waitFor(()=>$('job').textContent.includes('"ready": false'));
 assert.match($('job').textContent,/Set model/);
 $('baseline').click();
 await waitFor(()=>$('runs').textContent.includes('blocked'));
 dom.window.document.querySelector('#runs button').click();
 await waitFor(()=>$('report').textContent.includes('"status": "blocked"'));
 $('study').click();
 await waitFor(()=>$('runs').textContent.includes('study · blocked'));
 assert.deepEqual(errors,[]);
 process.stdout.write('PASS RSI DOM: Codex model selection (fixture), inference distinction; OpenAI login URL, cancel, unauthenticated models, provider state; initialization, artifacts, A/B plan, limits, blocked environment/baseline/study, no JS errors.\n');
 }finally{dom?.window.close();child.kill();rmSync(temp,{recursive:true,force:true});}
})().catch(e=>{process.stderr.write(e.stack+'\n');process.exitCode=1});
