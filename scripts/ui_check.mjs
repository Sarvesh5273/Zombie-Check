// Isolated headless Chrome QA; CDP blocks all audit mutation requests.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';

const origin = 'http://127.0.0.1:8765';
const auditId = process.argv[2] || '857949de-0d18-4951-9598-cef63cba4e55';
const artifactDir = path.resolve('artifacts');
const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'zombie-ui-'));
let browser, socket, send, sid;
const report = {generated_at:new Date().toISOString(),audit_id:auditId,mode:'read-only real audit UI',
  screenshots:[],checks:[],runtime_errors:[],blocked_mutations:[],cleanup_confirmed:false};
const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
const check = (name,passed,detail) => report.checks.push({name,passed:!!passed,detail});
try {
  await fs.mkdir(artifactDir,{recursive:true});
  browser = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ['--headless=new','--disable-gpu','--disable-background-networking','--hide-scrollbars','--no-first-run','--no-default-browser-check',
     '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:['ignore','ignore','pipe']});
  let stderr = '';
  browser.stderr.on('data',chunk=>{stderr=(stderr+chunk).slice(-10000)});
  const cdp = await new Promise((resolve,reject)=>{
    const deadline=Date.now()+20000;
    const timer=setInterval(()=>{
      const found=stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if(found){clearInterval(timer);resolve(found[1])}
      else if(Date.now()>deadline||browser.exitCode!==null){clearInterval(timer);reject(new Error('Isolated Chrome CDP startup failed'))}
    },100);
    browser.once('error',error=>{clearInterval(timer);reject(error)});
  });
  socket=new WebSocket(cdp);
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('CDP connection timeout')),10000);
    socket.addEventListener('open',()=>{clearTimeout(timer);resolve()},{once:true});
    socket.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('CDP connection failed'))},{once:true});
  });
  let sequence=0;
  const pending=new Map();
  socket.addEventListener('message',async event=>{
    const message=JSON.parse(String(event.data));
    if(message.id){
      const call=pending.get(message.id);
      if(call){pending.delete(message.id);clearTimeout(call.timer);message.error?call.reject(new Error(message.error.message)):call.resolve(message.result)}
    }else if(message.method==='Fetch.requestPaused'){
      const request=message.params.request, target=new URL(request.url);
      const allowed=request.method==='GET'||(request.method==='POST'&&target.pathname==='/api/preview');
      if(!allowed)report.blocked_mutations.push({method:request.method,path:target.pathname});
      try{await send(allowed?'Fetch.continueRequest':'Fetch.failRequest',{requestId:message.params.requestId,...(!allowed?{errorReason:'BlockedByClient'}:{})},message.sessionId)}
      catch(error){report.runtime_errors.push(error.message)}
    }else if(message.method==='Runtime.exceptionThrown'){
      report.runtime_errors.push(message.params.exceptionDetails.exception?.description||message.params.exceptionDetails.text);
    }
  });
  send=(method,params={},session)=>new Promise((resolve,reject)=>{
    const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(new Error(method+' timeout'))},20000);
    pending.set(id,{resolve,reject,timer});
    socket.send(JSON.stringify({id,method,params,...(session?{sessionId:session}:{})}));
  });
  const target=await send('Target.createTarget',{url:'about:blank'});
  sid=(await send('Target.attachToTarget',{targetId:target.targetId,flatten:true})).sessionId;
  await send('Page.enable',{},sid);
  await send('Runtime.enable',{},sid);
  await send('Fetch.enable',{patterns:[{urlPattern:origin+'/api/*',requestStage:'Request'}]},sid);
  const evaluate=async code=>{
    const r=await send('Runtime.evaluate',{expression:'(async()=>{'+code+'})()',awaitPromise:true,returnByValue:true},sid);
    if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);
    return r.result?.value;
  };
  const viewport=async(width,height,mobile=false)=>send('Emulation.setDeviceMetricsOverride',
    {width,height,deviceScaleFactor:1,mobile,screenWidth:width,screenHeight:height},sid);
  const capture=async name=>{
    const meta=await evaluate("return {width:innerWidth,height:innerHeight,status:typeof state==='undefined'?null:state.audit?.status,counts:typeof state==='undefined'?null:state.audit?.counts,audit_mode:typeof state==='undefined'?null:state.audit?.config?.mode,time:new Date().toISOString()};");
    const r=await send('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false},sid);
    const file=path.join(artifactDir,name);
    await fs.writeFile(file,Buffer.from(r.data,'base64'));report.screenshots.push({path:file,...meta});
  };
  const layout=()=>evaluate("return {width:innerWidth,document_width:document.documentElement.scrollWidth,body_width:document.body.scrollWidth};");
  await viewport(1440,1080);
  await send('Page.navigate',{url:origin},sid);
  for(let i=0;i<50;i++){if(await evaluate("return typeof selectAudit==='function'&&!!state.config;"))break;await sleep(100)}
  check('Server configuration loaded',await evaluate('return !!state.config;'),'Read-only local config endpoint.');
  let measured=await layout();check('Desktop welcome fits viewport',measured.document_width<=measured.width,measured);
  await capture('ui-desktop-welcome.png');
  const loaded=await evaluate('await selectAudit('+JSON.stringify(auditId)+');return {id:state.audit?.id,total:state.audit?.total,loaded:state.rows.length,rendered:document.querySelectorAll("#resultsBody tr").length};');
  check('Real ledger loads every original row (500+)',loaded.id===auditId&&loaded.total>=500&&loaded.loaded===loaded.total,loaded);
  check('Table renders a bounded page',loaded.rendered>0&&loaded.rendered<=25,loaded.rendered);
  measured=await layout();check('Desktop ledger fits viewport',measured.document_width<=measured.width,measured);
  await capture('ui-desktop-ledger.png');
  const filtered=await evaluate("setFilter('review');return {expected:state.rows.filter(r=>r.status==='review'||r.result?.review_required).length,actual:filteredRows().length};");
  check('Review filter matches actual rows',filtered.expected===filtered.actual,filtered);
  await capture('ui-desktop-reviews.png');
  const evidence=await evaluate("setFilter('all');const r=state.rows.find(r=>r.result&&r.result.signals_checked>=4)||state.rows[0];openDrawer(r.row_id,null);return {id:r.row_id,cards:document.querySelectorAll('#drawerBody .evidence-card').length,focus:document.activeElement.id};");
  check('Evidence drawer shows five signals',evidence.cards===5,evidence);
  check('Drawer receives keyboard focus',evidence.focus==='closeDrawer',evidence.focus);
  const mode=await evaluate("return {jobs:isJobMode(),labels:[...document.querySelectorAll('#drawerBody .evidence-card h3')].map(e=>e.innerText),postingIdentity:document.querySelector('#drawerBody').innerText.includes('POSTING IDENTITY'),limit:document.querySelector('#jobModeNote').innerText};");
  if(mode.jobs){
    check('Job mode uses exact-listing and intake labels',mode.labels.some(s=>s.includes('Exact job listing'))&&mode.labels.some(s=>s.includes('Application intake')),mode.labels);
    check('Job identity is described as posting identity',mode.postingIdentity,mode);
    check('Job alive limitation is visible',mode.limit.includes('funded vacancy')&&mode.limit.includes('completed hiring'),mode.limit);
  }
  await capture('ui-desktop-evidence.png');
  await evaluate('closeDrawer();await showReport();return true;');
  const gates=await evaluate("return {open:document.querySelector('#reportDialog').open,ready:state.report?.submission_ready,heading:document.querySelector('#reportBody .report-banner')?.innerText};");
  check('Report reflects its actual completion gates',gates.open&&typeof gates.ready==='boolean'&&(gates.ready?gates.heading.includes('gates passed'):gates.heading.includes('not ready')),gates);
  await capture('ui-desktop-report.png');
  const preview=await evaluate("document.querySelector('#reportDialog').close();const q=String.fromCharCode(34),quote=s=>q+String(s).replaceAll(q,q+q)+q;const csv=[state.audit.headers,...state.rows.slice(0,5).map(r=>r.original)].map(r=>r.map(quote).join(',')).join('\\n');showWelcome();await importContent(csv,'read-only-preview.csv');return {open:document.querySelector('#importDialog').open,rows:state.preview?.row_count};");
  check('CSV preview opens without creating audit',preview.open&&preview.rows===5,preview);
  const mapping=await evaluate("return {mode:effectiveImportMode(),selected:selectedJobColumns(),problems:mappingProblems(),nameHelp:document.querySelector('#nameColumnHelp').innerText,urlHelp:document.querySelector('#urlColumnHelp').innerText};");
  check('CSV mapping includes actual row examples',mapping.nameHelp.includes('Preview:')&&mapping.urlHelp.includes('Preview:'),mapping);
  if(mode.jobs){
    check('Job CSV auto detection and employer mapping are valid',mapping.mode==='jobs'&&Number.isInteger(mapping.selected?.employer)&&Number.isInteger(mapping.selected?.employer_website)&&Object.keys(mapping.problems).length===0,mapping);
    const validation=await evaluate("const csv=state.csv,select=document.querySelector('#employerColumn'),prior=select.value;select.value='';await createAudit({preventDefault(){}});const result={focused:document.activeElement.id,error:document.querySelector('#employerColumnError').innerText,invalid:select.getAttribute('aria-invalid'),summary:!document.querySelector('#importErrorSummary').hidden,csv_retained:state.csv===csv};select.value=prior;updateMappingPreview(true);updateBudgetExplanation();return result;");
    check('Invalid mapping gets focused summary and inline error without losing CSV',validation.focused==='importErrorSummary'&&validation.summary&&validation.invalid==='true'&&validation.error.includes('employer')&&validation.csv_retained,validation);
  }
  await capture('ui-desktop-import-preview.png');
  await evaluate("document.querySelector('#importDialog').close();await selectAudit("+JSON.stringify(auditId)+");return true;");
  await viewport(390,844,true);
  // Reload so the viewport meta tag and compositor adopt the mobile device.
  await send('Page.reload',{ignoreCache:true},sid);
  for(let i=0;i<100;i++){
    if(await evaluate("return innerWidth===390&&document.readyState==='complete'&&typeof selectAudit==='function'&&!!state.config;"))break;
    await sleep(100);
  }
  await evaluate("await selectAudit("+JSON.stringify(auditId)+");await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return true;");
  const diagnostic=await evaluate("return {innerWidth,clientWidth:document.documentElement.clientWidth,visual:visualViewport?.width,scale:visualViewport?.scale,overflows:[...document.querySelectorAll('*')].filter(e=>e.getClientRects().length&&e.getBoundingClientRect().right>395).map(e=>({tag:e.tagName,id:e.id,class:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width,overflow:getComputedStyle(e).overflow})).slice(0,25)};");
  report.mobile_diagnostic=diagnostic;
  measured=await layout();check('Mobile viewport is exactly390px',measured.width===390,measured);
  check('Mobile ledger fits viewport',measured.document_width<=390&&measured.body_width<=390,measured);
  await capture('ui-mobile-ledger.png');
  await evaluate("const r=state.rows.find(r=>r.result&&r.result.signals_checked>=4)||state.rows[0];openDrawer(r.row_id,null);return true;");
  const drawer=await evaluate("await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const r=document.querySelector('#evidenceDrawer').getBoundingClientRect();return {width:r.width,left:r.left,right:r.right,viewport:innerWidth};");
  check('Mobile drawer fits viewport',drawer.left>=0&&drawer.right<=391&&drawer.viewport===390,drawer);
  await capture('ui-mobile-evidence.png');
  await evaluate('closeDrawer();showWelcome();return true;');
  await capture('ui-mobile-welcome.png');
  check('No audit mutations attempted',report.blocked_mutations.length===0,report.blocked_mutations);
  check('No browser runtime exceptions',report.runtime_errors.length===0,report.runtime_errors);
}catch(error){report.error=error.message;process.exitCode=1}
finally{
  if(send&&socket?.readyState===WebSocket.OPEN){try{await send('Browser.close')}catch(error){report.cleanup_error=error.message}}
  try{socket?.close()}catch{}
  if(browser&&browser.exitCode===null){
    const ended=await Promise.race([new Promise(resolve=>browser.once('exit',()=>resolve(true))),sleep(4000).then(()=>false)]);
    if(!ended)browser.kill('SIGTERM');
  }
  if(browser){for(let i=0;browser.exitCode===null&&browser.signalCode===null&&i<20;i++)await sleep(100);report.cleanup_confirmed=browser.exitCode!==null||browser.signalCode!==null}
  else report.cleanup_confirmed=true;
  if(report.cleanup_confirmed)await fs.rm(profile,{recursive:true,force:true});
  else report.cleanup_error=report.cleanup_error||'Isolated Chrome exit not confirmed.';
  report.passed=report.checks.every(c=>c.passed)&&!report.error&&report.cleanup_confirmed;
  const file=path.join(artifactDir,'ui-check.json');await fs.writeFile(file,JSON.stringify(report,null,2));
  console.log(JSON.stringify({report:file,passed:report.passed,checks:report.checks.length,screenshots:report.screenshots.length,cleanup_confirmed:report.cleanup_confirmed,error:report.error||null}));
  if(!report.passed)process.exitCode=1;
}
