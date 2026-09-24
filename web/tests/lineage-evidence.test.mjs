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
const out=fs.mkdtempSync(path.join(os.tmpdir(),'lineage-evidence-'))
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
const {LifeChallenge}=require('./src/features/life/LifeChallenge.js')
const {LifeLedger}=require('./src/features/life/LifeLedger.js')
const {LineageEvidence}=require('./src/features/life/LineageEvidence.js')
const {I18nProvider}=require('./src/shared/i18n.js')
const {buildExperimentPlan}=require('./src/features/arena/experimentSetup.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))
async function withDOM(hash,fn){
 const dom=new JSDOM('<!doctype html><main id="root"></main>',{url:'https://arena.example/'+hash})
 const keys=['window','document','navigator','localStorage','location','history','sessionStorage','requestAnimationFrame','cancelAnimationFrame','matchMedia','IS_REACT_ACT_ENVIRONMENT','fetch']
 const originals=Object.fromEntries(keys.map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]))
 for(const key of keys.slice(0,7))Object.defineProperty(globalThis,key,{configurable:true,value:dom.window[key]})
 globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}})
 globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{};globalThis.IS_REACT_ACT_ENVIRONMENT=true
 const root=createRoot(document.getElementById('root'))
 try{await fn(dom,async(Component,props)=>{await act(async()=>root.render(React.createElement(I18nProvider,{key:localStorage.getItem('flyarena.locale')},React.createElement(Component,props))))})}
 finally{await act(async()=>root.unmount());dom.window.close();for(const [key,value] of Object.entries(originals)){if(value)Object.defineProperty(globalThis,key,value);else delete globalThis[key]}}
}
const noop=()=>{}
const fly={id:'a'.repeat(32),owner:'other',name:'Public individual',reference_kind:'user',spec:{model_profile:'malecns-lif-cpu-v1',connectome_sha256:'c'.repeat(64),description:'',weight_mutations:[],neuron_parameters:{tau_scale:1,threshold_shift_mv:0}},report:{budget_used:0,budget_limit:100}}
const own={...fly,id:'b'.repeat(32),owner:'owner',name:'My saved individual'}
const identity={id:'owner',token:'fixture'}
const button=text=>[...document.querySelectorAll('button')].find(el=>el.textContent===text)
async function choose(select,value){await act(async()=>{const key=Object.keys(select).find(k=>k.startsWith('__reactProps'));select[key].onChange({target:{value}})})}

test('public challenge chooses an owned saved individual, preserves exact opponent and only prepares',async()=>withDOM('#tab=life',async(dom,mount)=>{
 const calls=[],prepared=[]
 globalThis.fetch=async(url,options={})=>{calls.push([String(url),options.method||'GET']);return {ok:true,json:async()=>[own,fly]}}
 await mount(LifeChallenge,{fly,identity,onPrepare:(...args)=>prepared.push(args)})
 assert.equal(button('Prepare paired challenge').disabled,true)
 assert.deepEqual([...document.querySelector('select').options].map(o=>o.value),['',own.id])
 await choose(document.querySelector('select'),own.id)
 await act(async()=>button('Prepare paired challenge').click())
 assert.deepEqual(prepared,[[own,fly]]);assert.ok(calls.every(([,method])=>method==='GET'))
 const incompatible={...own,spec:{...own.spec,connectome_sha256:'different'}}
 globalThis.fetch=async()=>({ok:true,json:async()=>[incompatible]})
 await act(async()=>button('Refresh saved challengers').click());await choose(document.querySelector('select'),own.id)
 assert.equal(button('Prepare paired challenge').disabled,true)
 assert.match(document.body.textContent,/Different connectome/)
}))

test('challenge lists loading failures, refresh, missing ownership and bilingual empty state',async()=>withDOM('#tab=life',async(dom,mount)=>{
 globalThis.fetch=async()=>({ok:false,json:async()=>({detail:'Saved list unavailable'})})
 await mount(LifeChallenge,{fly,identity,onPrepare:noop})
 assert.match(document.body.textContent,/Saved list unavailable/);assert.equal(button('Prepare paired challenge').disabled,true)
 globalThis.fetch=async()=>({ok:true,json:async()=>[]})
 await act(async()=>button('Refresh saved challengers').click())
 assert.match(document.body.textContent,/No saved challengers/)
 await mount(LifeChallenge,{fly,identity:null,onPrepare:noop})
 assert.match(document.body.textContent,/Sign in and save your own fly/)
 localStorage.setItem('flyarena.locale','zh-CN')
 // Remount the provider to read the persisted language.
 await mount(()=>null,{})
 await mount(LifeChallenge,{fly,identity,onPrepare:noop})
 assert.match(document.body.textContent,/选择你保存的果蝇/)
}))

test('App life handoff builds the existing paired tournament against the exact public individual',()=>{
 const source=fs.readFileSync(path.join(web,'src/App.tsx'),'utf8')
 const callback=source.slice(source.indexOf("{tab==='life'" )).match(/onCompete=\{(.*?)\} onReplay=/)[1]
 const state={flies:[],duration:2}
 const setters=['setLifeComparisonFlies','setBranchFly','setSelected','setOpponent','setMode','setMapId','setDuration','setFocused','setPlay']
 const values=setters.map(name=>value=>{const key=name.slice(3,4).toLowerCase()+name.slice(4);state[key]=typeof value==='function'?value(state[key]):value})
 const prepare=Function(...setters,'flies','duration','matchingWildType','return '+callback)(...values,[],2,()=>null)
 prepare(own,fly)
 assert.equal(state.selected,own.id);assert.equal(state.opponent,fly.id);assert.equal(state.focused,'')
 const available=source.match(/const availableFlies=(.*)/)[1]
 const retained=Function('lifeComparisonFlies','branchFly','flies','return '+available)(state.lifeComparisonFlies,state.branchFly,[])
 assert.deepEqual(new Set(retained.map(f=>f.id)),new Set([own.id,fly.id]))
 const setup={...state,bridgeProfile:'legacy-v1',sensoryProfile:'odor-only-v1',seedText:'42'}
 const season={match_profiles:[{id:'legacy-v1',ready:true}]},maps=[{id:'orchard',modes:['forage','contest']}]
 const {plan,errors}=buildExperimentPlan(setup,state.lifeComparisonFlies,maps,season)
 assert.deepEqual(errors,[]);assert.equal(plan.submissions[0].endpoint,'/tournaments')
 assert.deepEqual(plan.matches.map(m=>m.fly_ids),[[own.id,fly.id],[fly.id,own.id]])
})

const delta={code:'unchanged',changed:false,changed_parameters:[],edge_changes:{count:0,edges:[]},intervention_changes:{count:0,items:[]}}
const evaluation=(id,score,status='verified')=>({match_id:id.repeat(32),condition:{map_id:'orchard',seed:0,duration_seconds:2,bridge_profile:'legacy-v1',sensory_profile:'odor-only-v1',motor:'frozen',runtime:'frozen'},status,scores:score===null?null:[score]})
const evidence={relatives:[{id:own.id,name:own.name,relation:'parent'}],parent_unavailable:false,next_offset:null,comparison:null}
const comparison={relative:own,relation:'parent',delta,left:[evaluation('c',0),evaluation('d',null,'failed')],right:[evaluation('e',1)],pairs:[{left:0,right:0,reasons:[]},{left:1,right:0,reasons:[{field:'status',code:'unverified'},{field:'motor',code:'missing'}]}]}

test('evidence shows comparable outcomes side by side and explains unverified or missing conditions',async()=>withDOM('#tab=life',async(dom,mount)=>{
 const calls=[]
 globalThis.fetch=async(url,options={})=>{calls.push(options.method||'GET');return {ok:true,json:async()=>({...evidence,comparison:String(url).includes('relative=')?comparison:null})}}
 await mount(LineageEvidence,{id:fly.id,identity})
 await choose(document.querySelector('select'),own.id)
 assert.match(document.body.textContent,/Comparable recorded pairs · 1/)
 assert.match(document.body.textContent,/Unmatched selected evaluations: 1/)
 const selectors=document.querySelectorAll('select')
 await choose(selectors[1],'0:0')
 assert.match(document.body.textContent,/Recorded score: 0/);assert.match(document.body.textContent,/Recorded score: 1/)
 assert.match(document.body.textContent,/Comparable recorded conditions; no causal or biological claim/)
 await choose(document.querySelectorAll('select')[2],'1')
 assert.match(document.body.textContent,/Not comparable/);assert.match(document.body.textContent,/Required evidence is missing/)
 assert.match(document.body.textContent,/Recorded status: failed/);assert.match(document.body.textContent,/Unavailable outcome/)
 assert.ok(calls.every(m=>m==='GET'))
}))

test('comparison failures remain visible and refresh retries without inventing outcomes',async()=>withDOM('#tab=life',async(dom,mount)=>{
 globalThis.fetch=async()=>({ok:false,json:async()=>({detail:'Evidence unavailable'})})
 await mount(LineageEvidence,{id:fly.id,identity})
 assert.match(document.body.textContent,/Comparison evidence failed to load/)
 globalThis.fetch=async()=>({ok:true,json:async()=>evidence})
 await act(async()=>button('Refresh comparison evidence').click())
 assert.doesNotMatch(document.body.textContent,/Evidence unavailable/)
 assert.match(document.body.textContent,/Choose a parent or child/)
}))

test('truncation opens a bounded slice with loading, failed refresh and return states',async()=>withDOM('#tab=life&fly='+fly.id,async(dom,mount)=>{
 const calls=[];let release;let fail=true
 const record={fly,can_annotate:false,origin:null,ancestors:[],descendants:[],notes:[],experiences:[]}
 const tree={center_id:fly.id,depth:3,edges:[],nodes:[{id:fly.id,label:fly.name,depth:0,relation:'center'},{id:'marker',label:'More',depth:1,relation:'descendants',marker:true,continuation:'/life/'+fly.id+'/slice?direction=descendants&offset=50'}]}
 globalThis.fetch=async(url,options={})=>{
  const value=String(url);calls.push([value,options.method||'GET'])
  if(value.includes('/slice?')&&fail)return await new Promise(resolve=>{release=()=>resolve({ok:false,json:async()=>({detail:'Slice unavailable'})})})
  const data=value.includes('/lineage?')?tree:value.includes('/slice?')?{...tree,nodes:[{id:own.id,label:'Next recorded child',depth:1,relation:'descendant'}]}:value.includes('/comparison?')?evidence:value.includes('/discover?')?{items:[],total:0,next_offset:null}:record
  return {ok:true,json:async()=>data}
 }
 await mount(LifeLedger,{identity:null,selected:fly.id,onBranch:noop,onCompete:noop,onReplay:noop})
 const marker=[...document.querySelectorAll('.life-tree-node button')].find(el=>el.textContent.includes('Load next bounded slice'))
 await act(async()=>marker.click())
 assert.match(document.body.textContent,/Loading lineage slice/)
 await act(async()=>release())
 assert.match(document.body.textContent,/Lineage slice failed to load/)
 fail=false;await act(async()=>button('Refresh lineage slice').click())
 assert.match(document.body.textContent,/Next recorded child/)
 await act(async()=>button('Return to selected lineage').click())
 assert.ok(document.querySelector('.life-tree-node.marker button'))
 assert.ok(calls.some(([url])=>url.endsWith('direction=descendants&offset=50')))
 assert.ok(calls.every(([,method])=>method==='GET'))
}))
