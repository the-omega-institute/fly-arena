// Synthetic UI-only regression: real production React/Three.js in an isolated
// browser. Every request is intercepted; no listener, backend or live auth used.
import assert from 'node:assert/strict'
import {readFile,mkdir,writeFile} from 'node:fs/promises'
import {resolve,extname} from 'node:path'
import {fileURLToPath} from 'node:url'
import {flies as fixtureFlies,catalog} from './ui-fixtures.mjs'
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'/tmp/fly-arena-browser-qa/node_modules/playwright/index.mjs')
const dist=fileURLToPath(new URL('../dist/',import.meta.url))
const output=process.env.QA_OUTPUT||'/tmp/fly-arena-ui-fix-v3'
await mkdir(output,{recursive:true})
const browser=await chromium.launch({headless:true})
const context=await browser.newContext({viewport:{width:1440,height:1100},locale:'en-US',colorScheme:'light'})
const page=await context.newPage()
await page.addInitScript(()=>{
 window.replayMismatches=[]
 new MutationObserver(()=>{
  const heading=document.querySelector('.stage-heading')?.textContent||''
  const score=document.querySelector('.score-overlay')?.textContent||''
  const id=heading.match(/TEST-[ABC]0[123]/)?.[0]
  if(id&&score&&(!score.includes(id+' Scene')||/TEST-[ABC]0[123]/g.test(score.replaceAll(id,''))))window.replayMismatches.push({heading,score})
 }).observe(document,{subtree:true,childList:true,characterData:true})
})
page.setDefaultTimeout(10000)
const errors=[],checks=[],requests=[],pending=[],aborted=[]
page.on('pageerror',e=>errors.push(e.message))
page.on('requestfailed',request=>{if(request.url().includes('/matches/'))aborted.push(new URL(request.url()).pathname)})
const ownA={...fixtureFlies[2],id:'TEST-own-A',name:'TEST Own A'}
const ownB={...ownA,id:'TEST-own-B',name:'TEST Own B'}
let flies=[...fixtureFlies.slice(0,2),ownA,ownB],submitted=null,archived=false
const ids=['TEST-A01','TEST-B02','TEST-C03','TEST-Q04']
const matches=ids.map((id,i)=>({id,status:i===3?'queued':'verified',progress:0,created:0,attempt:1,error:null,request:{fly_ids:[ownA.id,ownB.id],bridge_profile:i===1?'sensorimotor-research-v2':'legacy-v1',map_id:'TEST-arena',mode:'contest',seed:42+i,duration_seconds:[3,7,11,3][i]},result:i===3?null:{winner_slot:i===0?null:0,scores:[i+1,0],outcome:i===0?'draw':'win',receipt_sha256:'TEST-not-scientific-'+id}}))
const scene=id=>({body:{meshes:{},geoms:[]},size:12,obstacles:[],food:[],flies:[{id:id+'-fly',name:id+' Scene',color:'mint'}]})
const frames=id=>[0,matches.find(m=>m.id===id).request.duration_seconds].map(time=>({tick:time,time,poses:[],positions:[[time/4,0,0]],scores:[ids.indexOf(id)+1]}))
const modes=new Map(ids.map(id=>[id,'immediate']))
const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})
await page.route('**/*',async route=>{
 const request=route.request(),url=new URL(request.url()),path=url.pathname
 if(url.origin!=='https://fly-ui.test')return route.abort()
 if(!path.startsWith('/api/v1/')) {
   const local=path==='/'?'index.html':path.slice(1)
   assert.ok(!local.includes('..'))
   const body=await readFile(resolve(dist,local))
   return route.fulfill({body,contentType:({'.html':'text/html','.js':'application/javascript','.css':'text/css'})[extname(local)]||'application/octet-stream'})
 }
 const apiPath=path.slice('/api/v1'.length);requests.push({path:apiPath,method:request.method()})
 if(apiPath==='/auth/config')return json(route,{mode:'nyxid',nyxid_enabled:false,local_registration_enabled:false})
 if(apiPath==='/auth/session')return json(route,{authenticated:true,user:{id:'TEST-owner',name:'TEST Owner'},csrf_token:'TEST-fixture-only'})
 if(apiPath==='/season')return json(route,{id:'TEST-season',match_profiles:[{id:'legacy-v1',ready:true},{id:'sensorimotor-research-v2',ready:true}],default_bridge_profile:'legacy-v1',connectome:{sha256:'TEST-graph',neuron_count:100,edge_count:1000,circuits:[]},budget:{points:100},runtime_sha256:'TEST-runtime'})
 if(apiPath==='/flies')return json(route,flies)
 if(apiPath==='/maps')return json(route,[{id:'TEST-arena',name:'测试竞技场',english:'TEST Arena',size:12,color:'#ddd',obstacles:[],food:[],modes:['contest']}])
 if(apiPath==='/preview')return json(route,{body:{meshes:{},geoms:[]}})
 if(apiPath==='/leaderboard')return json(route,[])
 if(apiPath==='/matches')return json(route,archived?matches.filter(m=>m.id!==ids[2]):matches)
 if(apiPath.startsWith('/matches/')) {
   const [, ,id,kind]=apiPath.split('/')
   assert.ok(ids.includes(id));if(!kind)return json(route,matches.find(m=>m.id===id));assert.ok(['scene','frames'].includes(kind))
   const body=kind==='scene'?scene(id):frames(id)
   if(modes.get(id)==='hold'){pending.push({id,kind,route,body});return}
   return json(route,body)
 }
 if(apiPath==='/research/catalog')return json(route,catalog)
 if(apiPath==='/experiments'&&request.method()==='POST'){
   submitted=request.postDataJSON();assert.equal(request.headers()['x-arena-csrf'],'TEST-fixture-only')
   return json(route,{id:'TEST-created',status:'queued',spec:submitted})
 }
 if(apiPath==='/experiments')return json(route,[])
 if(apiPath==='/experiments/TEST-created')return json(route,{id:'TEST-created',owner:'TEST-owner',status:'queued',spec:submitted,subjects:[],reports:[],comparison:null})
 throw new Error('Unexpected fixture request '+request.method()+' '+apiPath)
})
const waitFor=async predicate=>{const end=Date.now()+10000;while(!await predicate()){assert.ok(Date.now()<end,'Timed out waiting for test condition');await new Promise(r=>setTimeout(r,20))}}
const focus=async id=>{await page.locator('.match-row').nth(ids.indexOf(id)).click();await waitFor(async()=>new URL(page.url()).hash.includes(id))}
const loaded=async id=>{await waitFor(async()=>(await page.locator('.score-overlay').innerText().catch(()=>'' )).includes(id+' Scene'));assert.match(await page.locator('.stage-heading').innerText(),/VERIFIED REPLAY/);assert.equal(await page.getByLabel('Replay position').getAttribute('max'),String(matches.find(m=>m.id===id).request.duration_seconds))}
const empty=async()=>{assert.equal(await page.locator('.score-overlay').count(),0);assert.equal(await page.locator('.fly-world-label').count(),0);assert.equal(await page.locator('.trace-panel').count(),0);assert.equal(await page.getByLabel('Replay position').isEnabled(),false);assert.doesNotMatch(await page.locator('.stage-heading').innerText(),/VERIFIED REPLAY/)}
const waiting=async id=>waitFor(()=>pending.filter(p=>p.id===id).length===2)
const release=async(id,failureKind)=>{
 const items=pending.filter(p=>p.id===id)
 pending.splice(0,pending.length,...pending.filter(p=>p.id!==id))
 for(const p of items)await json(p.route,p.kind===failureKind?{detail:'TEST 503 '+id+' '+p.kind}:p.body,p.kind===failureKind?503:200).catch(()=>{})
}
try {
 await page.goto('https://fly-ui.test/#tab=arena&match=TEST-A01')
 await page.locator('.preferences select').nth(0).selectOption('en')
 await loaded(ids[0])
 await page.getByLabel('Match fly',{exact:true}).selectOption(ownA.id)
 await page.getByRole('button',{name:'Design Studio',exact:true}).click()
 await page.locator('#fly-name').fill('TEST preserved unsaved draft')
 assert.ok(await page.getByText('Unsaved canonical draft',{exact:true}).count())
 await page.getByRole('button',{name:'Phenotype Lab',exact:true}).click()
 assert.equal(await page.getByLabel('Saved design',{exact:true}).inputValue(),ownA.id)
 await page.getByLabel('Saved design',{exact:true}).selectOption(ownB.id)
 for(let i=0;i<2;i++)await page.waitForResponse(r=>r.url().endsWith('/api/v1/flies'))
 assert.equal(await page.getByLabel('Saved design',{exact:true}).inputValue(),ownB.id)
 await page.getByRole('button',{name:'Run comparison',exact:true}).click()
 await waitFor(()=>submitted!==null);assert.equal(submitted.fly_id,ownB.id)
 await page.locator('.state-pill.queued').waitFor()
 assert.equal(await page.getByLabel('Saved design',{exact:true}).inputValue(),ownB.id)
 checks.push('Mounted Lab: explicit B survives two real 2.5-second refreshes while parent A remains selected; POST targets B and opening its report retains B')
 await page.getByLabel('Saved design',{exact:true}).selectOption(ownB.id)
 flies=flies.filter(f=>f.id!==ownB.id)
 await page.waitForResponse(r=>r.url().endsWith('/api/v1/flies'))
 await waitFor(async()=>await page.getByLabel('Saved design',{exact:true}).inputValue()==='')
 assert.equal(await page.getByRole('button',{name:'Run comparison',exact:true}).isEnabled(),false)
 flies.push(ownB);await page.waitForResponse(r=>r.url().endsWith('/api/v1/flies'))
 assert.equal(await page.getByLabel('Saved design',{exact:true}).inputValue(),'')
 checks.push('Removed explicit choice clears and disables submission; a later refresh does not silently restore it')
 await page.getByRole('button',{name:'Arena',exact:true}).click();await loaded(ids[0])
 modes.set(ids[1],'hold');await focus(ids[1]);await waiting(ids[1]);await empty()
 assert.match(await page.locator('.stage-heading').innerText(),/TEST-B02.*Experimental sensorimotor v2/)
 assert.match(await page.locator('.stage-message').innerText(),/Loading replay/)
 await page.screenshot({path:output+'/slow-B.png',fullPage:true})
 // Even one fulfilled endpoint must not render a partial replay.
 const one=pending.find(p=>p.id===ids[1]&&p.kind==='scene');await json(one.route,one.body)
 pending.splice(pending.indexOf(one),1);await empty()
 await release(ids[1]);await loaded(ids[1])
 assert.doesNotMatch(await page.locator('.score-overlay').innerText(),/TEST-A01/)
 checks.push('Slow A → B clears canvas, scores, traces and playback immediately; B appears only after both endpoints, with B profile and duration')
 for(const kind of ['scene','frames']) {
   await focus(ids[0]);await loaded(ids[0]);await focus(ids[1]);await waiting(ids[1]);await release(ids[1],kind)
   await waitFor(async()=>(await page.locator('.stage-message').innerText()).includes('Replay unavailable'))
   await empty();assert.match(await page.locator('.stage-message').innerText(),new RegExp('TEST 503 TEST-B02 '+kind))
 }
 checks.push('Either B endpoint returning HTTP 503 leaves B unavailable, without A data or result association')
 await page.locator('.preferences select').nth(1).selectOption('dark')
 await page.locator('.preferences select').nth(0).selectOption('zh-CN')
 assert.match(await page.locator('.stage-message').innerText(),/回放不可用/)
 await page.setViewportSize({width:390,height:844})
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))
 await page.screenshot({path:output+'/failed-B-dark-zh-mobile.png',fullPage:true})
 await page.locator('.preferences select').nth(0).selectOption('en')
 await page.locator('.preferences select').nth(1).selectOption('light')
 await page.setViewportSize({width:1440,height:1100})
 checks.push('Translated error state preserved in dark Chinese 390px layout without horizontal overflow')
 modes.set(ids[0],'hold');modes.set(ids[2],'hold')
 await focus(ids[0]);await waiting(ids[0]);await focus(ids[1]);await waiting(ids[1]);await focus(ids[2]);await waiting(ids[2]);await empty()
 await release(ids[2]);await loaded(ids[2])
 await release(ids[0]);await release(ids[1],'frames');await loaded(ids[2])
 assert.doesNotMatch(await page.locator('.score-overlay').innerText(),/TEST-A01|TEST-B02/)
 assert.equal(await page.locator('.error-banner').count(),0)
 assert.ok(aborted.some(p=>p.includes(ids[0])));assert.ok(aborted.some(p=>p.includes(ids[1])))
 checks.push('Rapid pending A → B → C aborts A/B; C remains correct after late A success and B failure')
 await focus(ids[1]);await waiting(ids[1]);await focus(ids[3]);await empty()
 assert.equal(await page.getByRole('button',{name:'Start match',exact:false}).isEnabled(),true)
 await release(ids[1],'scene');await empty()
 checks.push('Pending → queued clears loading ownership; late rejection neither poisons global errors nor leaves setup busy')
 modes.set(ids[2],'immediate');await focus(ids[2]);await loaded(ids[2])
 await page.goBack();await empty();await page.goForward();await loaded(ids[2])
 await page.screenshot({path:output+'/final-C-light-en.png',fullPage:true})
 checks.push('Browser back/forward restores matching replay identity and fresh playback')
 await page.getByRole('button',{name:'Design Studio',exact:true}).click()
 assert.equal(await page.locator('#fly-name').inputValue(),'TEST preserved unsaved draft')
 assert.ok(await page.getByText('Unsaved canonical draft',{exact:true}).count())
 checks.push('Unsaved design name and canonical draft identity survive Lab refresh/submission and replay navigation')
 archived=true;await page.goto('https://fly-ui.test/#tab=arena&match='+ids[2]);await loaded(ids[2])
 assert.equal(await page.locator('.match-row').count(),3)
 await page.waitForResponse(r=>r.url().endsWith('/api/v1/matches'));await loaded(ids[2])
 checks.push('Direct archived match URL loads metadata/replay outside the recent list and survives list refresh')
 assert.deepEqual(await page.evaluate(()=>window.replayMismatches),[])
 checks.push('DOM mutation observer detected zero transient match/scene identity mismatches')
 assert.deepEqual(errors,[])
 await writeFile(output+'/transitions.json',JSON.stringify({kind:'synthetic UI regression, not scientific evidence',checks,pageErrors:errors,abortedRequests:aborted,submitted,requests},null,2))
 console.log(JSON.stringify({checks,pageErrors:errors,output},null,2))
} finally {await browser.close()}
