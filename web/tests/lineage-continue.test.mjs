import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createRequire} from 'node:module'
import ts from 'typescript'
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {JSDOM} from 'jsdom'

const web=new URL('../',import.meta.url).pathname
const out=fs.mkdtempSync(path.join(os.tmpdir(),'lineage-continue-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web,'node_modules')),path.join(out,'node_modules'))
function compile(folder){
 for(const entry of fs.readdirSync(path.join(web,folder),{withFileTypes:true})){
  const relative=path.join(folder,entry.name),dest=path.join(out,relative.replace(/\.tsx?$/,'.js'))
  if(entry.isDirectory())compile(relative)
  else if(/\.tsx?$/.test(entry.name)){
   fs.mkdirSync(path.dirname(dest),{recursive:true})
   fs.writeFileSync(dest,ts.transpileModule(fs.readFileSync(path.join(web,relative),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText)
  }else if(entry.name.endsWith('.css')){fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,'')}
 }
}
compile('src')
const require=createRequire(path.join(out,'package.json'));require.extensions['.css']=()=>{}
const preview=require.resolve('./src/features/arena/MapPreview.js')
require.cache[preview]={id:preview,filename:preview,loaded:true,exports:{MapPreview:()=>null}}
const {continuationPlan,evaluationCount}=require('./src/features/training/plan.js')
const {continueLifeHash,continuationFocus}=require('./src/features/life/navigation.js')
const {TrainingSandbox}=require('./src/features/training/TrainingSandbox.js')
const {LifeLedger}=require('./src/features/life/LifeLedger.js')
const {I18nProvider}=require('./src/shared/i18n.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))
const fly={id:'a'.repeat(32),name:'Older public design',reference_kind:'user',spec:{model_profile:'malecns-lif-cpu-v1',connectome_sha256:'c'.repeat(64),description:'',weight_mutations:[],neuron_parameters:{tau_scale:1,threshold_shift_mv:0}},report:{budget_used:0,budget_limit:100}}
const rival={...fly,id:'b'.repeat(32)}
const season={connectome:{circuits:[]},training_bridge_profiles:[{id:'legacy-v1',ready:true,models:['malecns-lif-cpu-v1'],sensory_profiles:['odor-only-v1']},{id:'sensorimotor-research-v2',ready:false}],training_sensory_profiles:[{id:'odor-only-v1',ready:true}],training_fitness_objectives:[{id:'food',ready:true},{id:'sustained-foraging-v1',ready:true}]}
const maps=['orchard','maze','blank','labyrinth'].map(id=>({id,name:id,english:id,modes:id==='blank'?['forage']:['forage','contest']}))
const condition={match_id:'c'.repeat(32),status:'verified',map_id:'orchard',seed:0,mode:'forage',duration_seconds:7,bridge_profile:'legacy-v1',sensory_profile:'odor-only-v1',fitness_objective:'sustained-foraging-v1'}
const record=conditions=>({fly,continuation:{conditions,requires_copy:false}})
const build=(conditions,catalog=season,others=[rival])=>continuationPlan(record(conditions),catalog,maps,others)

test('continuation URLs roundtrip the selected individual, with no session or evaluation side effects',()=>{
 assert.equal(continuationFocus(continueLifeHash(fly.id)),fly.id)
 for(const hash of ['#tab=train','#tab=train&continue=../private','#tab=train&continue=not-an-id'])assert.equal(continuationFocus(hash),'')
})
test('retains exact recorded eligible conditions, zero seeds, objective and failed status',()=>{
 const input=[condition,{...condition,seed:91,status:'failed',match_id:'d'.repeat(32)}]
 const frozen=structuredClone(input),plan=build(input)
 assert.deepEqual(input,frozen)
 assert.equal(plan.founder_id,fly.id)
 assert.equal(plan.environment.fitness_objective,'sustained-foraging-v1')
 assert.deepEqual(plan.conditions,[{map_id:'orchard',seed:0},{map_id:'orchard',seed:91}])
 assert.match(plan.reviews[1].reason,/does not imply success/)
 assert.equal(evaluationCount({population:2,generations:1,mode:'forage',conditions:plan.conditions}),4)
})
test('reports unsupported, unready, changed, duplicate and excessive recorded setups without replacement',()=>{
 const input=[{...condition,map_id:'labyrinth'},{...condition,bridge_profile:'sensorimotor-research-v2'},condition,{...condition},
  {...condition,seed:1,duration_seconds:8},{...condition,seed:1},{...condition,seed:2},{...condition,seed:3},{...condition,seed:4}]
 const plan=build(input)
 assert.deepEqual(plan.conditions.map(c=>c.seed),[0,1,2,3])
 for(const [index,pattern] of [[0,/not eligible/],[1,/bridge/],[3,/Duplicate/],[4,/separate session/],[8,/at most four/]]){
  assert.equal(plan.reviews[index].retained,false);assert.match(plan.reviews[index].reason,pattern)
 }
})
test('missing evidence is not invented; readiness and compatibility are checked for every field',()=>{
 const {fitness_objective,sensory_profile,...missing}=condition
 const plan=build([missing]);assert.equal(plan.environment.fitness_objective,undefined);assert.equal(plan.environment.sensory_profile,undefined)
 for(const patch of [{status:'queued'},{bridge_profile:undefined},{seed:NaN},{seed:2147483648},{duration_seconds:31},{mode:'sumo'},{sensory_profile:'unavailable'},{fitness_objective:'unavailable'},{map_id:'missing'},{mode:'contest',opponent_id:'missing'}]){
  const result=build([{...condition,...patch}]);assert.equal(result.environment,null,JSON.stringify(patch));assert.equal(result.reviews[0].retained,false)
 }
 assert.equal(build([{...condition,mode:'contest',opponent_id:rival.id}]).conditions.length,1)
 const bad={...rival,spec:{...rival.spec,model_profile:'incompatible'}}
 assert.equal(build([{...condition,mode:'contest',opponent_id:rival.id}],season,[bad]).conditions.length,0)
 assert.deepEqual(build([]).conditions,[])
})

// DOM lifetime belongs to each test, so Node 22 cannot run a top-level after hook
// before a later test has finished using globals.
async function withDOM(hash,fn){
 const dom=new JSDOM('<!doctype html><main id="root"></main>',{url:'https://arena.example/'+hash})
 const keys=['window','document','navigator','localStorage','location','history','sessionStorage','requestAnimationFrame','cancelAnimationFrame','matchMedia','IS_REACT_ACT_ENVIRONMENT','fetch']
 const originals=Object.fromEntries(keys.map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]))
 for(const key of keys.slice(0,7))Object.defineProperty(globalThis,key,{configurable:true,value:dom.window[key]})
 globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}})
 globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{};globalThis.IS_REACT_ACT_ENVIRONMENT=true
 const root=createRoot(document.getElementById('root'))
 try{await fn(dom,async(Component,props)=>{await act(async()=>root.render(React.createElement(I18nProvider,null,React.createElement(Component,props))))})}
 finally{await act(async()=>root.unmount());dom.window.close();for(const [key,value] of Object.entries(originals)){if(value)Object.defineProperty(globalThis,key,value);else delete globalThis[key]}}
}
const noop=()=>{}
const props={flies:[],identity:{id:'owner',token:'fixture'},selected:rival.id,season,maps,onLogin:noop,onSaved:async()=>{},onCompete:noop,onReplay:noop}
const byLabel=text=>[...document.querySelectorAll('.training-setup label')].find(el=>el.textContent.startsWith(text)).querySelector('input,select')
const startButton=()=>[...document.querySelectorAll('button')].find(el=>el.textContent.includes('Start training'))

test('training loads an older individual outside the fly list and waits for explicit finite-budget Start',async()=>withDOM(continueLifeHash(fly.id),async(dom,mount)=>{
 const requests=[];let posted
 globalThis.fetch=async(url,options={})=>{
  requests.push([String(url),options.method||'GET']);let data=[]
  if(String(url).endsWith('/lives/'+fly.id))data=record([condition,{...condition,seed:19}])
  if(options.method==='POST'){posted=JSON.parse(options.body);return {ok:false,json:async()=>({detail:'Fixture stops before execution'})}}
  return {ok:true,json:async()=>data}
 }
 await mount(TrainingSandbox,props)
 assert.equal(byLabel('Starting fly').value,fly.id)
 assert.equal(byLabel('Starting fly').disabled,true)
 assert.equal(byLabel('Environment').value,'orchard')
 assert.equal(document.getElementById('training-fitness-objective').value,'sustained-foraging-v1')
 assert.equal(byLabel('Seconds per evaluation').value,'7')
 assert.equal(startButton().disabled,false)
 assert.ok(requests.every(([,method])=>method==='GET'))
 await act(async()=>startButton().click())
 assert.equal(posted.founder_id,fly.id);assert.equal(posted.seed,0)
 assert.equal(posted.duration_seconds,7);assert.equal(posted.bridge_profile,'legacy-v1')
 assert.deepEqual(posted.evaluation_conditions,[{map_id:'orchard',seed:0},{map_id:'orchard',seed:19}])
 assert.equal(posted.population,2);assert.equal(posted.generations,1);assert.equal(posted.max_evaluations,4)
 assert.match(document.body.textContent,/Fixture stops before execution/)
}))
test('missing objective blocks Start and bilingual review does not claim a recorded default',async()=>withDOM(continueLifeHash(fly.id),async(dom,mount)=>{
 const {fitness_objective,...missing}=condition
 globalThis.fetch=async url=>({ok:true,json:async()=>String(url).endsWith('/lives/'+fly.id)?record([missing]):[]})
 localStorage.setItem('flyarena.locale','zh-CN')
 await mount(TrainingSandbox,props)
 assert.equal(document.getElementById('training-fitness-objective').value,'')
 assert.match(document.body.textContent,/未记录选择目标/)
 assert.ok([...document.querySelectorAll('button')].find(el=>el.textContent.includes('开始训练')).disabled)
}))
test('failed or inaccessible continuation fetch never starts a default founder',async()=>withDOM(continueLifeHash(fly.id),async(dom,mount)=>{
 const posts=[]
 globalThis.fetch=async(url,options={})=>{if(options.method==='POST')posts.push(url);return String(url).includes('/lives/')?{ok:false,json:async()=>({detail:'Life record not found'})}:{ok:true,json:async()=>[]}}
 await mount(TrainingSandbox,props)
 assert.equal(byLabel('Starting fly').value,'');assert.equal(startButton().disabled,true)
 assert.match(document.body.textContent,/Life record not found/);assert.deepEqual(posts,[])
}))
test('a portable snapshot is copied explicitly and catalog refresh preserves the reviewed branch',async()=>withDOM(continueLifeHash(fly.id),async(dom,mount)=>{
 const copied={...fly,id:'e'.repeat(32),spec:{...fly.spec,parent_id:fly.id}}
 const sample={...fly,source:{kind:'published-training',run_id:'f'.repeat(32)}}
 const posts=[];const saved=[]
 globalThis.fetch=async(url,options={})=>{
  let data=[]
  if(String(url).endsWith('/lives/'+fly.id))data={fly:sample,continuation:{conditions:[condition],requires_copy:true}}
  if(options.method==='POST'){posts.push(String(url));assert.ok(String(url).endsWith('/copy'));data=copied}
  return {ok:true,json:async()=>data}
 }
 const copyProps={...props,season:{...season,gallery_copy_available:true},onSaved:async fly=>saved.push(fly)}
 await mount(TrainingSandbox,copyProps)
 assert.equal(startButton().disabled,true);assert.deepEqual(posts,[])
 await act(async()=>[...document.querySelectorAll('button')].find(el=>el.textContent==='Save a copy and prepare training').click())
 assert.equal(saved[0].spec.parent_id,fly.id);assert.equal(byLabel('Starting fly').value,copied.id)
 assert.equal(startButton().disabled,false)
 // App.onSaved refreshes both catalog objects as well as the fly list.
 await mount(TrainingSandbox,{...copyProps,flies:[copied],season:structuredClone(copyProps.season),maps:structuredClone(maps)})
 assert.equal(byLabel('Starting fly').value,copied.id);assert.equal(startButton().disabled,false)
 assert.equal(document.getElementById('training-fitness-objective').value,condition.fitness_objective)
 assert.equal(posts.length,1)
}))
test('every accessible lineage node has its own continuation link; archive searches and pages on the server',async()=>withDOM('#tab=life&fly='+fly.id,async(dom,mount)=>{
 const calls=[];const full={fly,origin:null,ancestors:[],descendants:[],notes:[],experiences:[],can_annotate:false}
 globalThis.fetch=async url=>{
  const value=String(url);calls.push(value);let data=full
  if(value.includes('/lives/discover?'))data={items:[fly],total:201,next_offset:value.includes('offset=25')?50:25}
  if(value.includes('/lineage?'))data={center_id:fly.id,depth:3,edges:[],nodes:[{id:fly.id,label:fly.name,depth:0,relation:'center'},{id:rival.id,label:'Sibling',depth:0,relation:'sibling'},{id:'redacted:private',label:'Private',depth:1,relation:'descendant',redacted:true},{id:'marker',label:'More',depth:2,relation:'descendant',marker:true}]}
  return {ok:true,json:async()=>data}
 }
 await mount(LifeLedger,{identity:null,selected:fly.id,onBranch:noop,onCompete:noop,onReplay:noop})
 assert.deepEqual([...document.querySelectorAll('.life-tree-node a')].map(el=>el.getAttribute('href')).sort(),[continueLifeHash(fly.id),continueLifeHash(rival.id)].sort())
 const next=[...document.querySelectorAll('button')].find(el=>el.textContent==='Next page')
 await act(async()=>next.click());assert.ok(calls.some(url=>url.includes('offset=25')))
 const input=document.querySelector('.life-index>input')
 await act(async()=>{const key=Object.keys(input).find(key=>key.startsWith('__reactProps'));input[key].onChange({target:{value:'old name'}})})
 assert.ok(calls.some(url=>url.includes('query=old+name')&&url.includes('offset=0')))
}))
