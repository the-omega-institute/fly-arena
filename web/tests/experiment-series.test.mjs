import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createRequire} from 'node:module'
import ts from 'typescript'
import React,{act} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {createRoot} from 'react-dom/client'
import {JSDOM} from 'jsdom'

const web=new URL('../',import.meta.url).pathname,out=fs.mkdtempSync(path.join(os.tmpdir(),'experiment-series-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web,'node_modules')),path.join(out,'node_modules'))
function compile(folder){for(const entry of fs.readdirSync(path.join(web,folder),{withFileTypes:true})){
 const relative=path.join(folder,entry.name)
 if(entry.isDirectory())compile(relative)
 else if(/\.tsx?$/.test(entry.name)){const dest=path.join(out,relative.replace(/\.tsx?$/,'.js'));fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,ts.transpileModule(fs.readFileSync(path.join(web,relative),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText)}
 else if(entry.name.endsWith('.css')){const dest=path.join(out,relative);fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,'')}
}}
compile('src')
const require=createRequire(path.join(out,'package.json'));require.extensions['.css']=()=>{}
const {ExperimentSeries,ArenaSeries}=require('./src/features/arena/ExperimentSeries.js')
const {I18nProvider}=require('./src/shared/i18n.js')
const {readRoute,routeHash}=require('./src/shared/navigation.js')
const {duelMessages}=require('./src/shared/messages/duel.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))
const flies=[{id:'a',name:'Design'},{id:'b',name:'Reference'}]
const fixture=(status='running')=>({id:'series-1',owner:'me',created:1,spec:{name:'Synthetic fixture',fly_ids:['a','b'],seeds:[42],map_id:'orchard',mode:'contest',duration_seconds:2},status,expected_matches:2,verified_matches:1,issues:[],unexpected_match_ids:[],standings:[],matches:[{id:'leg-1',status:'verified'},{id:'leg-2',status:'queued'}],schedule:[{seed:42,spawn_order:1,fly_ids:['a','b'],status:'verified',match_ids:['leg-1'],outcomes:[{fly_id:'a',score:2,outcome:'win'},{fly_id:'b',score:1,outcome:'loss'}],issues:[],errors:[]},{seed:42,spawn_order:2,fly_ids:['b','a'],status:'queued',match_ids:['leg-2'],outcomes:null,issues:[],errors:[]}]})
// DOM globals live inside each test and are restored only after React unmounts.
async function withDOM(run){
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://arena.example/#tab=arena&series=series-1'})
 const keys=['window','document','navigator','localStorage','location','history','sessionStorage','matchMedia','IS_REACT_ACT_ENVIRONMENT','fetch','requestAnimationFrame','cancelAnimationFrame']
 const originals=Object.fromEntries(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const k of keys.slice(0,7))Object.defineProperty(globalThis,k,{configurable:true,writable:true,value:dom.window[k]})
 globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});globalThis.IS_REACT_ACT_ENVIRONMENT=true;globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{}
 const root=createRoot(document.getElementById('root'))
 const render=async(Component,props)=>act(async()=>root.render(React.createElement(I18nProvider,null,React.createElement(Component,props))))
 try{await run({root,render,dom})}finally{await act(async()=>root.unmount());dom.window.close();for(const [k,d]of Object.entries(originals)){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k]}}
}

test('series deep links round trip with replay context and encoded IDs',()=>{
 const hash=routeHash('arena','','match & 1','series + 2'),route=readRoute(hash)
 assert.equal(route.series,'series + 2');assert.equal(route.match,'match & 1');assert.equal(route.tab,'arena')
 assert.equal(readRoute('#series=historical').tab,'arena');assert.equal(routeHash('arena','','','id'),'#tab=arena&series=id')
})
test('every scheduled row is shown while first-leg outcomes never become a conclusion',()=>{
 const series=fixture(),html=renderToStaticMarkup(React.createElement(ExperimentSeries,{series,flies}))
 assert.equal((html.match(/<tr>/g)||[]).length,3)
 assert.match(html,/leg-1/);assert.match(html,/match=leg-1&amp;series=series-1/)
 assert.match(html,/series.partial/);assert.doesNotMatch(html,/series-conclusion/)
 series.status='incomplete';series.schedule[1].status='failed';series.schedule[1].errors=['Measured worker failure'];series.schedule[1].issues=['failed_match']
 const failed=renderToStaticMarkup(React.createElement(ExperimentSeries,{series,flies}))
 assert.match(failed,/Measured worker failure/);assert.match(failed,/series.status.failed/);assert.doesNotMatch(failed,/series-conclusion/)
 series.schedule[1]={...series.schedule[1],status:'missing',match_ids:[],errors:[],issues:['missing_match']}
 const missing=renderToStaticMarkup(React.createElement(ExperimentSeries,{series,flies}))
 assert.match(missing,/series.status.missing/);assert.doesNotMatch(missing,/match=leg-2/)
})
test('a complete report renders one aggregate conclusion, scoped copy and per-fly totals',async()=>withDOM(async({render})=>{
 const series=fixture('complete');series.standings=[{fly_id:'a',played:2,wins:1,draws:0,losses:1,points:3},{fly_id:'b',played:2,wins:1,draws:0,losses:1,points:3}]
 await render(ExperimentSeries,{series,flies})
 assert.equal(document.querySelectorAll('.series-conclusion').length,1)
 assert.match(document.body.textContent,/1 wins · 0 draws · 1 losses · 3 points/)
 assert.match(document.body.textContent,/not a global ranking/)
 assert.match(document.body.textContent,/do not establish general superiority/)
}))
test('series recovers by ID independently of recent matches and preserves recent owner links',async()=>withDOM(async({render})=>{
 const calls=[];globalThis.fetch=async url=>{calls.push(String(url));return {ok:true,json:async()=>String(url).includes('?owner=')?[fixture(),{...fixture(),id:'someone-else',owner:'other'}]:fixture()}}
 await render(ArenaSeries,{seriesId:readRoute(location.hash).series,identity:{id:'me'},flies})
 assert.ok(calls.includes('/api/v1/tournaments/series-1'));assert.ok(calls.includes('/api/v1/tournaments?owner=me'))
 assert.match(document.body.textContent,/a first-leg win remains a first-leg result/)
 const list=document.querySelector('[aria-label="Your recent series"]')
 assert.equal(list.querySelectorAll('a').length,1);assert.equal(list.querySelector('a').getAttribute('href'),'#tab=arena&series=series-1')
}))
test('switching series discards late old responses and shows retrieval failures',async()=>withDOM(async({render})=>{
 let resolveOld
 globalThis.fetch=async url=>String(url).endsWith('/series-1')?new Promise(resolve=>{resolveOld=resolve}):{ok:false,json:async()=>({detail:'Not found fixture'})}
 await render(ArenaSeries,{seriesId:'series-1',identity:null,flies})
 assert.match(document.body.textContent,/Loading series/)
 await render(ArenaSeries,{seriesId:'missing',identity:null,flies})
 await act(async()=>resolveOld({ok:true,json:async()=>fixture('complete')}))
 assert.match(document.body.textContent,/Not found fixture/);assert.doesNotMatch(document.body.textContent,/Synthetic fixture/)
}))
test('Chinese series strings and failure reasons come from the duel module',async()=>withDOM(async({render})=>{
 for(const [key,value]of Object.entries(duelMessages).filter(([key])=>key.startsWith('series.'))){assert.ok(value.en,key);assert.ok(value['zh-CN'],key)}
 localStorage.setItem('flyarena.locale','zh-CN')
 const series=fixture('incomplete');series.issues=['condition_mismatch'];series.schedule[1].status='mismatched';series.schedule[1].issues=['condition_mismatch']
 await render(ExperimentSeries,{series,flies})
 assert.match(document.body.textContent,/配对系列结果/);assert.match(document.body.textContent,/首局获胜仍只是首局结果/);assert.match(document.body.textContent,/比赛条件与保存的系列不同/)
 assert.doesNotMatch(document.body.textContent,/series\./)
}))
test('App submission retains the tournament ID and recovers it after remount',async()=>withDOM(async({render,root})=>{
 for(const [name,exports]of [['ArenaCanvas',{ArenaCanvas:()=>null}],['features/arena/MapPreview',{MapPreview:()=>null}],['features/arena/useReplay',{useReplay:()=>({scene:null,frames:[],events:[],status:'idle',error:''})}]]){const file=require.resolve('./src/'+name+'.js');require.cache[file]={id:file,filename:file,loaded:true,exports}}
 // Keep the real App submission path; the setup stub supplies an ordinary validated plan.
 const spec={connectome_sha256:'a'.repeat(64),model_profile:'malecns-lif-cpu-v1',weight_mutations:[],edge_deltas:[],neuron_parameters:{tau_scale:1,threshold_shift_mv:0}}
 const entrants=[{id:'a'.repeat(32),name:'Design',color:'mint',owner:'me',spec},{id:'b'.repeat(32),name:'WT',color:'mint',owner:'server',reference_kind:'wildtype',spec}]
 const season={connectome:{sha256:'a'.repeat(64),neuron_count:1,edge_count:1,circuits:[]},budget:{points:100},match_profiles:[{id:'legacy-v1',ready:true}],default_bridge_profile:'legacy-v1'}
 const maps=[{id:'orchard',name:'Orchard',english:'Orchard',modes:['contest','forage'],food:[],obstacles:[],size:28}]
 const {buildExperimentPlan}=require('./src/features/arena/experimentSetup.js')
 const plan=buildExperimentPlan({selected:entrants[0].id,opponent:entrants[1].id,mapId:'orchard',mode:'contest',duration:2,seedText:'42',bridgeProfile:'legacy-v1',sensoryProfile:'odor-only-v1'},entrants,maps,season).plan
 const file=require.resolve('./src/features/arena/ExperimentSetupPanel.js');require.cache[file]={id:file,filename:file,loaded:true,exports:{ExperimentSetup:props=>React.createElement('button',{onClick:()=>props.startMatch(plan)},'Submit fixture series')}}
 delete require.cache[require.resolve('./src/features/arena/ArenaFeature.js')]
 delete require.cache[require.resolve('./src/App.js')]
 const App=require('./src/App.js').default
 history.replaceState(null,'','#tab=arena');localStorage.setItem('flyarena.identity',JSON.stringify({id:'me',token:'fixture-token'}))
 let writes=0
 globalThis.fetch=async(url,options={})=>{
  const path=String(url).replace('/api/v1','')
  if(options.method==='POST'){assert.equal(path,'/tournaments');writes++;return {ok:true,json:async()=>({...fixture(),matches:plan.matches.map((request,i)=>({id:'leg-'+(i+1),status:'queued',progress:0,request}))})}}
  const data=path==='/auth/config'?{mode:'local'}:path==='/me'?{id:'me',name:'Fixture'}:path==='/flies'?entrants:path==='/season'?season:path==='/maps'?maps:path==='/preview'?{}:path==='/tournaments/series-1'?fixture():path.startsWith('/tournaments?')?[fixture()]:[]
  return {ok:true,json:async()=>data}
 }
 await render(App,{})
 await act(async()=>[...document.querySelectorAll('button')].find(el=>el.textContent==='Submit fixture series').click())
 assert.equal(writes,1);assert.equal(location.hash,'#tab=arena&series=series-1');assert.match(document.body.textContent,/Synthetic fixture/)
 await act(async()=>root.render(null));await render(App,{})
 assert.equal(writes,1);assert.match(document.body.textContent,/Synthetic fixture/);assert.match(document.body.textContent,/a first-leg win remains a first-leg result/)
}))
