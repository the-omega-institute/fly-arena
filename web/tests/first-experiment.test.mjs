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
const out=fs.mkdtempSync(path.join(os.tmpdir(),'first-experiment-'))
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
const {I18nProvider}=require('./src/shared/i18n.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))
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

const spec={model_profile:'malecns-lif-cpu-v1',connectome_sha256:'c'.repeat(64),parent_id:'baseline',weight_mutations:[],edge_deltas:[],neuron_parameters:{tau_scale:1,threshold_shift_mv:0}}
const fly={id:'a'.repeat(32),name:'Saved design',owner:'me',reference_kind:'user',spec,report:{budget_used:0,budget_limit:100}}
const wt={...fly,id:'b'.repeat(32),name:'Reference',owner:'server',reference_kind:'wildtype'}
const maps=[{id:'orchard',name:'果园',english:'Orchard',modes:['forage','contest']}]
const season={connectome:{sha256:spec.connectome_sha256,circuits:[]},match_profiles:[{id:'legacy-v1',ready:true}]}
const first={id:'first',status:'verified',request:{fly_ids:[fly.id,wt.id],map_id:'orchard',mode:'contest',seed:42,duration_seconds:2},result:{receipt_sha256:'receipt',scores:[0,0]}}
const second={...first,id:'second',request:{...first.request,fly_ids:[wt.id,fly.id]}}
const noop=()=>{}
const {FirstExperimentGuide}=require('./src/features/training/FirstExperimentGuide.js')
const {trainingMessages}=require('./src/shared/messages/training.js')
const {catalog}=require('./src/shared/messages.js')
const props={fly,flies:[fly,wt],maps,season,matches:[],budget:4,needed:4,duration:5,onCompare:noop,onReplay:noop,onConfigure:noop}
const button=()=>document.querySelector('.first-experiment-guide button')

test('all first-experiment copy is bilingual and registered in the existing catalog',()=>{
 for(const [key,value] of Object.entries(trainingMessages).filter(([key])=>key.startsWith('training.first.'))){
  for(const locale of ['en','zh-CN']){assert.ok(value[locale]);assert.equal(catalog[key][locale],value[locale])}
 }
})
for(const locale of ['en','zh-CN'])test(`selected fly offers baseline or finite optimization without starting work in ${locale}`,async()=>withDOM('',async(dom,mount)=>{
 localStorage.setItem('flyarena.locale',locale)
 globalThis.fetch=()=>{throw Error('Choice must not submit evaluations')}
 const plans=[],configured=[]
 await mount(FirstExperimentGuide,{...props,onCompare:p=>plans.push(p),onConfigure:()=>configured.push(true)})
 assert.match(document.body.textContent,/Saved design/)
 for(const key of ['budgetMeaning','results','saved'])assert.ok(document.body.textContent.includes(trainingMessages['training.first.'+key][locale]))
 await act(async()=>button().click())
 assert.equal(plans.length,1);assert.equal(plans[0].setup.selected,fly.id);assert.equal(plans[0].setup.opponent,wt.id)
 assert.equal(plans[0].matches.length,2)
 await act(async()=>document.querySelectorAll('.first-experiment-guide button')[1].click())
 assert.deepEqual(configured,[true]);assert.equal(plans.length,1)
 assert.doesNotMatch(document.body.textContent,/training\.first\./)
}))
test('a complete WT comparison opens recorded replay; failed/partial evidence prepares a new plan',async()=>withDOM('',async(dom,mount)=>{
 const opened=[],plans=[]
 await mount(FirstExperimentGuide,{...props,matches:[first,second],onReplay:m=>opened.push(m),onCompare:p=>plans.push(p)})
 assert.equal(button().textContent,'Inspect recorded WT comparison')
 await act(async()=>button().click());assert.deepEqual(opened,[first]);assert.deepEqual(plans,[])
 await mount(FirstExperimentGuide,{...props,matches:[first,{...second,status:'failed'}],onReplay:m=>opened.push(m),onCompare:p=>plans.push(p)})
 assert.equal(button().textContent,'Prepare WT comparison')
 await act(async()=>button().click());assert.equal(plans.length,1);assert.equal(opened.length,1)
}))
test('changing the selected fly recomputes compatibility and the finite budget display',async()=>withDOM('',async(dom,mount)=>{
 await mount(FirstExperimentGuide,props)
 assert.equal(button().disabled,false)
 const incompatible={...fly,id:'other',name:'Rate fly',spec:{...spec,model_profile:'malecns-rate-cpu-v1'}}
 await mount(FirstExperimentGuide,{...props,fly:incompatible,flies:[incompatible,wt],budget:8,needed:16,duration:10})
 assert.equal(button().disabled,true)
 assert.match(document.body.textContent,/Rate fly/)
 assert.match(document.body.textContent,/Evaluation cap: 8 · Planned evaluations: 16 × 10 s/)
 await mount(FirstExperimentGuide,{...props,fly:undefined,budget:NaN,needed:Infinity})
 assert.ok([...document.querySelectorAll('button')].every(b=>b.disabled))
 assert.doesNotMatch(document.body.textContent,/NaN|Infinity/)
}))
// Verify the guide is connected to the actual training founder selector and explicit Start gate.
const preview=require.resolve('./src/features/arena/MapPreview.js')
require.cache[preview]={id:preview,filename:preview,loaded:true,exports:{MapPreview:()=>null}}
const {TrainingSandbox}=require('./src/features/training/TrainingSandbox.js')
test('saving destination uses the selected founder and preparation never posts training or matches',async()=>withDOM('#tab=train',async(dom,mount)=>{
 const requests=[],plans=[]
 globalThis.fetch=async(url,options={})=>{requests.push([String(url),options.method||'GET']);return {ok:true,json:async()=>[]}}
 dom.window.HTMLElement.prototype.scrollIntoView=noop
 await mount(TrainingSandbox,{flies:[wt,fly],selected:fly.id,identity:{id:'me'},maps,season,matches:[],onCompareWT:p=>plans.push(p),onSaved:async()=>{},onCompete:()=>assert.fail('Use explicit plan path'),onReplay:noop,onLogin:noop})
 assert.equal(document.querySelector('.training-layout').firstElementChild.classList.contains('first-experiment-guide'),true)
 await act(async()=>button().click())
 assert.equal(plans[0].setup.selected,fly.id)
 await act(async()=>document.querySelectorAll('.first-experiment-guide button')[1].click())
 assert.equal(document.activeElement.id,'training-fitness-objective')
 const select=[...document.querySelectorAll('.training-setup label')].find(el=>el.textContent.startsWith('Starting fly')).querySelector('select')
 await act(async()=>{select.value=wt.id;select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.equal(button().disabled,true)
 assert.ok(requests.every(([,method])=>method==='GET'))
}))
