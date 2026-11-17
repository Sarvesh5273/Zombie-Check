// Continuous recording of the real app. All audit mutations are blocked.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'recording');
const origin = 'http://127.0.0.1:8765';
const auditId = '857949de-0d18-4951-9598-cef63cba4e55';
const targetRowId = 'R000329';
const resumeProofUrl = pathToFileURL(path.join(root,'artifacts/jobs-resume-proof.json')).href;
const runtimeModules = '/Users/sarvesh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const digest = value => crypto.createHash('sha256').update(typeof value === 'string' ? value : JSON.stringify(value)).digest('hex');
const proof = { started_at: new Date().toISOString(), audit_id: auditId, target_row_id: targetRowId,
  scope: 'Continuous real app recording of an audit completed earlier',
  allowed_requests: [], blocked_requests: [], actions: [], segments: [], runtime_errors: [], screenshots: [],
  injected_product_data: false, audit_mutations_allowed: false, paid_service_calls: 0 };

await fs.mkdir(output, {recursive:true});
// Use full local FFmpeg: this Playwright version records VP8, while its cached
// minimal FFmpeg only includes VP9. Never alter the user's global runtime.
const browsersPath = path.join(output, '.runtime');
await fs.mkdir(browsersPath, {recursive:true});
await fs.mkdir(path.join(browsersPath,'ffmpeg-1011'),{recursive:true});
try { await fs.symlink('/opt/homebrew/bin/ffmpeg', path.join(browsersPath, 'ffmpeg-1011/ffmpeg-mac')); }
catch (error) { if (error.code !== 'EEXIST') throw error; }
process.env.PLAYWRIGHT_BROWSERS_PATH = browsersPath;
const { chromium } = await import(path.join(runtimeModules, 'playwright/index.mjs'));

// This helper only reads local audit data for the no-mutation comparison.
async function localGet(route) {
  const response = await fetch(origin + route, {method:'GET'});
  if (!response.ok) throw new Error(`GET ${route}: HTTP ${response.status}`);
  return response.json();
}
async function baseline() {
  const audit = await localGet(`/api/audits/${auditId}`);
  const rows = await localGet(`/api/audits/${auditId}/rows?limit=500&offset=0`);
  const audits = await localGet('/api/audits');
  return {audit, rows, audit_ids: audits.audits.map(a => a.id).sort(),
    audit_sha256: digest(audit), rows_sha256: digest(rows)};
}

let browser, context, page, rawVideo;
let start, pointer = {x:80,y:70};
const elapsed = () => (performance.now() - start) / 1000;
async function mark(label, operation, details={}) {
  const item={label,start_seconds:elapsed(),...details};
  proof.actions.push(item);
  await operation();
  item.end_seconds=elapsed();
}
async function hold(label, seconds) {
  const item={label,start_seconds:elapsed()};
  proof.segments.push(item);
  await sleep(seconds*1000);
  item.end_seconds=elapsed();
}
async function moveTo(locator) {
  await locator.scrollIntoViewIfNeeded();
  const box=await locator.boundingBox();
  if (!box) throw new Error('Missing visible target for pointer movement');
  const end={x:box.x+box.width*.5,y:box.y+box.height*.5};
  const from={...pointer}, steps=24;
  for(let step=1;step<=steps;step++) {
    const t=step/steps, eased=t*t*(3-2*t);
    await page.mouse.move(from.x+(end.x-from.x)*eased,from.y+(end.y-from.y)*eased);
    await sleep(12);
  }
  pointer=end;
}
async function click(selector) {
  const locator=page.locator(selector);
  await moveTo(locator);
  await page.mouse.click(pointer.x,pointer.y,{delay:90});
}
async function selectNative(selector, value) {
  const locator=page.locator(selector);
  await moveTo(locator);
  // Playwright's native select action selects an existing option and dispatches
  // the ordinary input/change events. It never invokes app functions or submits.
  await locator.selectOption(value);
  await sleep(350);
}
async function scrollAt(selector, delta, duration=1200) {
  await moveTo(page.locator(selector));
  const steps=30;
  for(let i=0;i<steps;i++) { await page.mouse.wheel(0,delta/steps); await sleep(duration/steps); }
  await sleep(300);
}
async function shot(name) {
  const file=path.join(output,name+'.png');
  await page.screenshot({path:file});
  proof.screenshots.push({path:file,seconds:elapsed()});
}

try {
  proof.before=await baseline();
  if(proof.before.audit.status!=='complete'||proof.before.rows.total!==500) throw new Error('Saved completed 500-row audit is required');
  const targetRow=proof.before.rows.rows.find(row=>row.row_id===targetRowId);
  if(!targetRow?.result?.public_page_check?.resolved_by_locale) throw new Error('Exact locale-recovery evidence row is missing');
  proof.target_row={row_id:targetRow.row_id,title:targetRow.result.current_job_title,
    verdict:targetRow.result.verdict,canonical_url:targetRow.result.identity.canonical_url};
  browser=await chromium.launch({executablePath:chrome,headless:true,
    args:['--disable-background-networking','--no-first-run','--no-default-browser-check']});
  context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1,
    recordVideo:{dir:path.join(output,'raw'),size:{width:1920,height:1080}},acceptDownloads:true,
    locale:'en-US',timezoneId:'Asia/Kolkata'});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    const local=url.origin===origin;
    const allowed=(local&&(request.method()==='GET'||(request.method()==='POST'&&url.pathname==='/api/preview')))
      ||(request.method()==='GET'&&request.url()===resumeProofUrl);
    const item={method:request.method(),url:request.url(),seconds:start?elapsed():null};
    if(allowed) { proof.allowed_requests.push(item); await route.continue(); }
    else { proof.blocked_requests.push(item); await route.abort('blockedbyclient'); }
  });
  // Capture-only pointer: position is updated exclusively by real mouse events.
  // No app content, counts, dates, results, or other display data is injected.
  await context.addInitScript(()=>{
    addEventListener('DOMContentLoaded',()=>{
      const cursor=document.createElement('div');
      cursor.setAttribute('aria-hidden','true');
      cursor.style.cssText='position:fixed;left:-50px;top:-50px;width:12px;height:12px;border:2px solid white;border-radius:50%;background:#202820;pointer-events:none;z-index:2147483647;';
      document.body.appendChild(cursor);
      addEventListener('mousemove',event=>{cursor.style.left=(event.clientX-6)+'px';cursor.style.top=(event.clientY-6)+'px';},{passive:true});
    },{once:true});
  });
  start=performance.now();
  page=await context.newPage();
  page.on('pageerror',error=>proof.runtime_errors.push(error.message));
  rawVideo=page.video();
  await mark('Open actual app',async()=>{await page.goto(origin,{waitUntil:'networkidle'});await page.locator('.audit-nav').first().waitFor();});
  await page.mouse.move(pointer.x,pointer.y);
  await hold('Welcome — original list and five signals',4);
  await shot('01-welcome');
  await mark('Upload actual 500-row CSV through the file input',async()=>{
    await moveTo(page.locator('#dropZone'));
    await page.locator('#fileInput').setInputFiles(path.join(root,'examples/jobs-500.csv'));
    await page.locator('#importDialog[open]').waitFor();
    if(!(await page.locator('#importFileMeta').innerText()).includes('500')) throw new Error('Real CSV preview did not show 500 rows');
  },{file:'examples/jobs-500.csv'});
  await hold('Real import preview',3);
  await mark('Choose job-post mode with the actual select control',()=>selectNative('#auditMode','jobs'));
  await mark('Map original job title column',()=>selectNative('#nameColumn','1'));
  await mark('Map exact original job URL column',()=>selectNative('#urlColumn','2'));
  await mark('Map original employer column',()=>selectNative('#employerColumn','0'));
  await mark('Map original employer website column',()=>selectNative('#employerWebsiteColumn','4'));
  const mappings=await page.locator('#importForm').evaluate(form=>Object.fromEntries(
    ['auditMode','nameColumn','urlColumn','employerColumn','employerWebsiteColumn'].map(id=>[id,form.querySelector('#'+id).value])));
  proof.import_mappings=mappings;
  if(JSON.stringify(mappings)!==JSON.stringify({auditMode:'jobs',nameColumn:'1',urlColumn:'2',employerColumn:'0',employerWebsiteColumn:'4'}))
    throw new Error('Actual native column mappings did not match the original CSV');
  await hold('Original title, URL, employer, and website examples',3);
  await mark('Inspect optional job-board mappings',()=>click('.job-advanced-mapping summary'));
  await mark('Scroll real import form to preview and cost cap',()=>scrollAt('#importDialog .modal-body',560));
  await hold('Original CSV cells and research cost cap',4);
  await shot('02-import-preview');
  await mark('Close preview without creating an audit',()=>click('[data-close="importDialog"]'));
  await mark('Open saved completed audit from the sidebar',async()=>{
    await click(`[data-audit="${auditId}"]`);
    await page.locator('#auditView:not([hidden])').waitFor();
    await page.waitForFunction(()=>document.getElementById('checkedCount').textContent==='500');
  });
  await hold('Completed earlier — actual 500-row totals',6);
  await shot('03-completed-ledger');
  await mark('Filter alive rows',()=>click('[data-filter="alive"]'));
  await hold('Actual alive rows and five signal indicators',3);
  await mark('Filter slowing-down rows',()=>click('[data-filter="slowing down"]'));
  await hold('Actual slowing-down rows',4);
  await mark('Restore all rows and search for exact posting 8113562',async()=>{
    await click('[data-filter="all"]');
    await click('#rowSearch');
    await page.keyboard.type('8113562',{delay:110});
    await page.locator(`[data-row="${targetRowId}"]`).waitFor();
  });
  await hold('Exact original posting found',2);
  await mark('Open exact row R000329',()=>click(`[data-row="${targetRowId}"]`));
  await page.locator('#evidenceDrawer:not([hidden])').waitFor();
  await hold('Reason, cautious verdict, preserved failed route, and recovered locale',7);
  await shot('04-locale-recovery');
  await mark('Inspect employer blog and release evidence',()=>scrollAt('#drawerBody',550));
  await hold('Employer dates, methods, and real source links',4);
  await shot('05-employer-evidence');
  await mark('Inspect exact listing, social uncertainty, and application intake',()=>scrollAt('#drawerBody',610));
  await hold('Independent job and application checks; uncertainty is visible',6);
  await shot('06-posting-intake');
  await mark('Close evidence',()=>click('#closeDrawer'));
  await mark('Clear exact-posting search',async()=>{
    await click('#rowSearch');await page.keyboard.press('Meta+A');await page.keyboard.press('Backspace');
  });
  await mark('Open actual run report',async()=>{await click('#viewReport');await page.locator('#reportDialog[open]').waitFor();});
  await hold('Actual completion gates and meaningful service usage',6);
  await shot('07-run-report');
  await mark('Inspect report scope and preserved row count',()=>scrollAt('#reportBody',430));
  await hold('Original rows and observation limits',3);
  await mark('Close run report',()=>click('[data-close="reportDialog"]'));
  await mark('Download actual CSV from the app',async()=>{
    const downloadPromise=page.waitForEvent('download');
    await click('#exportCsv');
    const download=await downloadPromise;
    const file=path.join(output,'downloaded-audit.csv');await download.saveAs(file);
    proof.download={path:file,suggested_filename:download.suggestedFilename(),sha256:digest(await fs.readFile(file,'utf8'))};
  });
  await hold('Actual export confirmation and completed ledger',3);
  await shot('08-export-complete');
  await mark('Open actual saved resume proof in the browser file view',async()=>{
    await page.goto(resumeProofUrl,{waitUntil:'load'});
    await page.locator('body').waitFor();
  },{file:'artifacts/jobs-resume-proof.json'});
  await hold('Recorded checkpoint proof — 490 preserved, 500 completed',6);
  await shot('09-actual-resume-proof');
  await mark('Return to real completed app ledger',async()=>{
    await page.goto(origin,{waitUntil:'networkidle'});
    await click(`[data-audit="${auditId}"]`);
    await page.waitForFunction(()=>document.getElementById('checkedCount').textContent==='500');
  });
  await hold('Final actual completed ledger',Math.max(3,95-elapsed()));
  await shot('10-final-ledger');
  proof.recording_wall_seconds=elapsed();
  proof.after=await baseline();
  proof.comparison={audit_unchanged:proof.before.audit_sha256===proof.after.audit_sha256,
    rows_unchanged:proof.before.rows_sha256===proof.after.rows_sha256,
    no_new_audits:JSON.stringify(proof.before.audit_ids)===JSON.stringify(proof.after.audit_ids)};
  proof.passed=Object.values(proof.comparison).every(Boolean)&&proof.blocked_requests.length===0&&proof.runtime_errors.length===0;
  for(const key of ['before','after']) {
    const b=proof[key];
    proof[key]={audit_id:b.audit.id,status:b.audit.status,total:b.rows.total,row_count:b.rows.rows.length,
      counts:b.audit.counts,audit_ids:b.audit_ids,audit_sha256:b.audit_sha256,rows_sha256:b.rows_sha256};
  }
} catch(error) {
  proof.error=error.stack||error.message;proof.passed=false;process.exitCode=1;
} finally {
  if(page) await page.close().catch(error=>{proof.runtime_errors.push(error.message);});
  if(rawVideo) {try {
    proof.raw_video=await rawVideo.path();
    const stat=await fs.stat(proof.raw_video);if(stat.size===0) throw new Error('Raw screen recording is empty');
    proof.raw_video_bytes=stat.size;
  }catch(error){proof.error=proof.error||error.message;proof.passed=false;}}
  if(context) await context.close().catch(()=>{});
  if(browser) await browser.close().catch(()=>{});
  proof.finished_at=new Date().toISOString();
  await fs.writeFile(path.join(output,'capture-proof.json'),JSON.stringify(proof,null,2)+'\n');
  await fs.writeFile(path.join(output,'action-timestamps.json'),JSON.stringify({audit_id:auditId,scope:proof.scope,
    capture_wall_seconds:proof.recording_wall_seconds,actions:proof.actions,segments:proof.segments},null,2)+'\n');
}

if(proof.passed&&proof.raw_video) {
  const mp4=path.join(output,'app-recording-silent.mp4');
  const log=await fs.open(path.join(output,'encode.log'),'w');
  const command=['-hide_banner','-y','-i',proof.raw_video,'-an','-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p','-r','30','-movflags','+faststart',mp4];
  const code=await new Promise((resolve,reject)=>{
    const child=spawn('/opt/homebrew/bin/ffmpeg',command,{stdio:['ignore',log.fd,log.fd]});
    child.once('error',reject);child.once('exit',resolve);
  });
  await log.close();
  if(code!==0) throw new Error('Continuous MP4 encoding failed');
  proof.silent_mp4=mp4;
  await fs.writeFile(path.join(output,'capture-proof.json'),JSON.stringify(proof,null,2)+'\n');
}
console.log(JSON.stringify({passed:proof.passed,raw_video:proof.raw_video,silent_mp4:proof.silent_mp4,
  duration_seconds:proof.recording_wall_seconds,action_count:proof.actions.length,blocked_requests:proof.blocked_requests.length,
  comparison:proof.comparison,error:proof.error||null}));
