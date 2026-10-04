// DOM integration test against an isolated real Flask server; no browser layout check.
const {JSDOM, VirtualConsole} = require('jsdom');
const {spawn} = require('node:child_process');
const {mkdtempSync, rmSync} = require('node:fs');
const {tmpdir} = require('node:os');
const path = require('node:path');
const net = require('node:net');
const assert = require('node:assert/strict');
async function waitFor(fn) {
 const end = Date.now()+10000;
 while(Date.now()<end) { if(await fn()) return; await new Promise(resolve=>setTimeout(resolve,20)); }
 throw Error('Timeout waiting for UI');
}
(async()=>{
 const temp = mkdtempSync(path.join(tmpdir(),'neuropilot-ui-'));
 const socket = net.createServer(); await new Promise(resolve=>socket.listen(0,'127.0.0.1',resolve));
 const port = socket.address().port; await new Promise(resolve=>socket.close(resolve));
 const base = `http://127.0.0.1:${port}`;
 const server = spawn(process.env.PYTHON || 'python3',['-c',`import server; server.app.run(host='127.0.0.1',port=${port},debug=False)`], {cwd:path.resolve(__dirname,'..'),env:{...process.env,NEUROPILOT_DATA:path.join(temp,'data.json')},stdio:'ignore'});
 let dom;
 try {
  await waitFor(async()=>{try{return (await fetch(base+'/health')).ok}catch{return false}});
  const errors = []; const console = new VirtualConsole(); console.on('jsdomError',e=>errors.push(e.message));
  dom = await JSDOM.fromURL(base, {resources:'usable',runScripts:'dangerously',virtualConsole:console,beforeParse(window){window.fetch=(url,options)=>fetch(new URL(url,base),options); window.confirm=()=>true;}});
  const document=dom.window.document; const $=id=>document.getElementById(id);
  await waitFor(()=>$('ask')?.onclick);
  $('note').value='Chci se učit Python'; $('ask').click();
  await waitFor(()=>document.querySelector('#notes article'));
  assert.match($('out').textContent,/Odpověď/);
  $('taskInput').value='Úkol <script>alert(1)</script>'; $('addTask').click();
  await waitFor(()=>document.querySelector('#tasks li'));
  assert.equal(document.querySelector('#tasks script'),null);
  document.querySelector('#tasks button').click();
  await waitFor(()=>document.querySelector('#tasks span').style.textDecoration==='line-through');
  $('habitTitle').value='Číst 10 minut'; $('addHabit').click();
  await waitFor(()=>document.querySelector('#habits button'));
  document.querySelector('#habits button').click();
  await waitFor(()=>document.querySelector('#habits p').textContent.includes('1/7'));
  const data=await (await fetch(base+'/export')).json();
  assert.equal(data.tasks[0].done,true); assert.equal(data.notes.length,1); assert.equal(data.habits[0].records.length,1);
  const backup={notes:[],tasks:[{id:123,text:'Imported'}],habits:[]};
  Object.defineProperty($('importFile'),'files',{value:[{text:async()=>JSON.stringify(backup)}]});
  $('importData').click(); await waitFor(()=>document.querySelector('#tasks span')?.textContent==='Imported');
  document.querySelector('#tasks button:last-child').click(); await waitFor(()=>$('tasks').children.length===0);
  assert.deepEqual(errors,[]);
  process.stdout.write('PASS: real-server DOM integration — chat, tasks, literal HTML, habits, export, import, deletion; no JS errors.\n');
 } finally {dom?.window.close();server.kill();rmSync(temp,{recursive:true,force:true});}
})().catch(error=>{process.stderr.write(error.stack+'\n');process.exitCode=1;});
