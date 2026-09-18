import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createRequire} from 'node:module'
import ts from 'typescript'
import React, {act} from 'react'
import {createRoot} from 'react-dom/client'
import {JSDOM} from 'jsdom'

// Exercise real React controls in a DOM. No browser, GPU or simulation job is needed.
const web=new URL('../',import.meta.url).pathname
const out=fs.mkdtempSync(path.join(os.tmpdir(),'playground-controls-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web,'node_modules')),path.join(out,'node_modules'))
function compile(folder){
 for(const entry of fs.readdirSync(path.join(web,folder),{withFileTypes:true})){
  const relative=path.join(folder,entry.name)
  if(entry.isDirectory())compile(relative)
  else if(/\.tsx?$/.test(entry.name)){
   const output=ts.transpileModule(fs.readFileSync(path.join(web,relative),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}})
   const dest=path.join(out,relative.replace(/\.tsx?$/,'.js'));fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,output.outputText)
  }else if(entry.name.endsWith('.css')){const dest=path.join(out,relative);fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,'')}
 }
}
compile('src')
const require=createRequire(path.join(out,'package.json'));require.extensions['.css']=()=>{}
const {PlaygroundGuide}=require('./src/features/guide/PlaygroundGuide.js')
const {WildTypeChallenge}=require('./src/features/arena/WildTypeChallenge.js')
const {matchingWildType,wildTypeChallenge}=require('./src/features/arena/wildtype.js')
const {DevelopersFeature}=require('./src/features/developers/DevelopersFeature.js')
const {I18nProvider,Preferences}=require('./src/shared/i18n.js')
const dom=new JSDOM('<!doctype html><html><body><main id="root"></main></body></html>',{url:'http://arena.example/'})
const originals=Object.fromEntries(['window','document','navigator','localStorage','matchMedia','IS_REACT_ACT_ENVIRONMENT','fetch'].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
for(const k of ['window','document','navigator','localStorage'])Object.defineProperty(globalThis,k,{configurable:true,value:dom.window[k]})
globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}})
globalThis.IS_REACT_ACT_ENVIRONMENT=true
globalThis.fetch=()=>{throw Error('An onboarding control unexpectedly requested network/compute')}
let root=createRoot(document.getElementById('root'))
const spec={schema_version:'flyspec/v1',name:'My fly',description:'',color:'mint',parent_id:null,connectome_sha256:'a'.repeat(64),model_profile:'malecns-lif-cpu-v1',weight_mutations:[],edge_deltas:[],neuron_parameters:{tau_scale:1,threshold_shift_mv:0},plasticity:'none'}
const wt={id:'a'.repeat(32),name:'Canonical reference',spec,reference_kind:'wildtype'}
const own={id:'b'.repeat(32),name:'My saved fly',spec:{...spec,parent_id:wt.id},reference_kind:'user'}
const noop=()=>{}
const button=label=>{const el=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===label||b.getAttribute('aria-label')===label);assert.ok(el,`Missing button: ${label}`);return el}
async function click(label){await act(async()=>button(label).click())}
async function mount(Component,props){await act(async()=>root.render(React.createElement(I18nProvider,null,React.createElement(Preferences),React.createElement(Component,props))))}
test.afterEach(async()=>{await act(async()=>root.unmount());document.getElementById('root').replaceChildren();root=createRoot(document.getElementById('root'));localStorage.clear()})
test.after(async()=>{await act(async()=>root.unmount());dom.window.close();fs.rmSync(out,{recursive:true,force:true});for(const [k,d]of Object.entries(originals)){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k]}})

test('a novice can clone, edit, train, compare and open AI help without launching work',async()=>{
 const calls=[];const props={canCloneWT:true,hasSavedDesign:false,neuronCount:123,onCloneWT:()=>calls.push('clone'),onDesign:()=>calls.push('edit'),onTrain:()=>calls.push('train'),onArena:()=>calls.push('compare'),onAI:()=>calls.push('ai')}
 await mount(PlaygroundGuide,props)
 assert.match(document.body.textContent,/123/)
 for(const label of ['Use WT','Open design','Train','Compare','Connect an AI'])await click(label)
 assert.deepEqual(calls,['clone','edit','train','compare','ai'])
 await click('Collapse playground guide');assert.ok(!document.querySelector('.playground-guide__steps'))
 await mount(PlaygroundGuide,props);assert.ok(!document.querySelector('.playground-guide__steps'))
 await click('Reopen playground guide');assert.ok(document.querySelector('.playground-guide__steps'))
 assert.ok(document.querySelector('a[href="https://male-cns.janelia.org/"]'))
 assert.match(document.body.textContent,/not identical to a real animal/)
})
test('guide handles unavailable WT and switches all instructions with the global language',async()=>{
 await mount(PlaygroundGuide,{canCloneWT:false,hasSavedDesign:false,onCloneWT:noop,onDesign:noop,onTrain:noop,onArena:noop,onAI:noop})
 assert.equal(button('Use WT').disabled,true)
 assert.ok(!document.querySelector('.playground-guide__count'))
 const language=document.querySelector('select[aria-label="Language"]')
 await act(async()=>{language.value='zh-CN';language.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(document.body.textContent,/编辑并保存/)
 assert.match(document.body.textContent,/模拟基线/)
})
test('WT shortcut uses recorded provenance and compatible graph/model, never a spoofed name',()=>{
 const spoof={...own,name:'Wild Type / 原型'}
 const incompatible={...wt,spec:{...spec,connectome_sha256:'c'.repeat(64)}}
 assert.equal(matchingWildType([spoof,incompatible,wt],own),wt)
 assert.equal(wildTypeChallenge([spoof,incompatible],spoof.id),null)
 assert.equal(wildTypeChallenge([wt,own],wt.id),null)
 assert.equal(wildTypeChallenge([wt,own],'missing'),null)
 assert.equal(wildTypeChallenge([{...wt,spec:{...spec,model_profile:'other'}},own],own.id),null)
})
test('WT challenge prepares the exact visible small preset and requires a saved non-WT subject',async()=>{
 const plans=[]
 await mount(WildTypeChallenge,{flies:[wt,own],selected:'',onPrepare:p=>plans.push(p)})
 assert.equal(button('Prepare WT challenge').disabled,true)
 await mount(WildTypeChallenge,{flies:[wt,own],selected:own.id,onPrepare:p=>plans.push(p)})
 assert.match(document.body.textContent,/4 simulated seconds total/)
 await click('Prepare WT challenge')
 assert.deepEqual(plans,[{subject:own,reference:wt,map_id:'orchard',mode:'contest',duration_seconds:2,seed:42}])
})
test('AI instructions copy the actual origin without credentials and survive clipboard failure',async()=>{
 let copied='';let identityRequests=0
 Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async value=>{copied=value}}})
 const props={jsonEditor:'',setJsonEditor:noop,spec,download:noop,fileInput:{current:null},loadSpec:noop,setError:noop,identity:{id:'owner',name:'Private name',token:'DO-NOT-COPY-TOKEN'},setShowToken:()=>identityRequests++,setLogin:noop}
 await mount(DevelopersFeature,props)
 await click('Copy task prompt')
 assert.match(copied,/http:\/\/arena.example\/api\/v1\/agent-guide/)
 assert.match(copied,/http:\/\/arena.example\/openapi.json/)
 assert.doesNotMatch(copied,/DO-NOT-COPY-TOKEN|Private name/)
 assert.equal(identityRequests,0)
 assert.match(document.body.textContent,/Task prompt copied/)
 assert.match(document.body.textContent,/POST \/api\/v1\/matches/)
 navigator.clipboard.writeText=async()=>{throw Error('Clipboard unavailable')}
 await click('Copy task prompt');assert.match(document.body.textContent,/Copy failed; select the text manually/)
 assert.ok(document.querySelector('.prompt-card textarea').value.includes('/agent-guide'))
})
test('AI JSON editing retains import errors and does not publish or enqueue on open',async()=>{
 const loaded=[];const errors=[]
 const props={jsonEditor:JSON.stringify(spec),setJsonEditor:noop,spec,download:noop,fileInput:{current:null},loadSpec:value=>loaded.push(value),setError:value=>errors.push(value),identity:null,setShowToken:noop,setLogin:noop}
 await mount(DevelopersFeature,props)
 await click('Open in Studio');assert.deepEqual(loaded,[spec])
 await mount(DevelopersFeature,{...props,jsonEditor:'{broken json'})
 await click('Open in Studio');assert.equal(errors.length,1);assert.equal(loaded.length,1)
 const language=document.querySelector('select[aria-label="Language"]')
 await act(async()=>{language.value='zh-CN';language.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.ok(button('复制任务提示'))
})

test('optimizer cards select CEM and custom model with clear runtime semantics',async()=>{
 const {AlgorithmPicker}=require('./src/features/training/AlgorithmPicker.js')
 const changes=[];const names=[]
 await mount(AlgorithmPicker,{value:'evolution',onChange:v=>changes.push(v),name:'My model',onName:v=>names.push(v)})
 assert.equal(document.querySelectorAll('input[type=radio]').length,4)
 await act(async()=>document.querySelector('input[value=cross_entropy]').click())
 assert.deepEqual(changes,['cross_entropy'])
 await mount(AlgorithmPicker,{value:'external',onChange:v=>changes.push(v),name:'My model',onName:v=>names.push(v)})
 assert.equal(document.querySelector('input[type=radio][value=external]').checked,true)
 assert.ok([...document.querySelectorAll('input')].some(i=>i.value==='My model'))
 assert.match(document.body.textContent,/same connectome LIF simulator/)
 const language=document.querySelector('select[aria-label="Language"]')
 await act(async()=>{language.value='zh-CN';language.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(document.body.textContent,/自定义算法/)
})

test('public gallery exposes real generations and branches without starting compute',async()=>{
 const {TrainingShowcase}=require('./src/features/training/TrainingShowcase.js')
 const requests=[];const branched=[]
 const fly={...own,report:{budget_used:1},spec:{...spec,weight_mutations:[{selector:'olfactory',scale:1.1}]}}
 const run={id:'c'.repeat(32),status:'complete',spec:{name:'Real CEM',strategy:'cross_entropy',founder_id:wt.id,opponent_id:null,map_id:'orchard',mode:'forage',seed:42,duration_seconds:1,population:2,generations:2,max_evaluations:4,circuits:['olfactory'],mutation_strength:.08},baseline_fitness:0,evaluation_context:'runtime',evaluations_completed:4,evaluations_started:4,evaluations_total:4,best_fly_id:fly.id,members:[{generation:0,slot:0,fitness:0,fly_id:wt.id,fly:{...fly,id:wt.id},matches:[],condition_results:[]},{generation:1,slot:1,fitness:.25,fly_id:fly.id,fly,matches:[],condition_results:[]}]}
 globalThis.fetch=async(url,options)=>{requests.push([url,options?.method||'GET']);return {ok:true,json:async()=>[run]}}
 await mount(TrainingShowcase,{maps:[],onReplay:noop,onBranch:f=>branched.push(f)})
 assert.equal(requests.length,1);assert.match(String(requests[0][0]),/training-showcase/)
 assert.match(document.body.textContent,/Real CEM/)
 await click('G21 evaluated')
 assert.match(document.body.textContent,/0.250/)
 await click('Use as starting fly');assert.equal(branched[0].id,fly.id)
 assert.deepEqual(requests.map(r=>r[1]),['GET'])
 globalThis.fetch=()=>{throw Error('Unexpected network')}
})
