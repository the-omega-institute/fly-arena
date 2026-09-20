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
// Real controls/data are exercised below; WebGL rasterization is a separate acceptance step.
let spatialCanvasProps=null
const spatialCanvasFile=require.resolve('./src/features/arena/AnatomicalBrainCanvas.js')
require.cache[spatialCanvasFile]={id:spatialCanvasFile,filename:spatialCanvasFile,loaded:true,exports:{AnatomicalBrainCanvas:props=>{
 spatialCanvasProps=props
 return React.createElement('div',{'data-spatial-canvas':true},props.nodes.filter(n=>n.position).map(n=>React.createElement('button',{key:n.id,'aria-label':'Spatial neuron '+n.id,'data-activity':n.activity===null?'missing':String(n.activity),onClick:()=>props.onFocus(n.id)},n.id)))
}}}
const {PlaygroundGuide}=require('./src/features/guide/PlaygroundGuide.js')
const {WildTypeChallenge}=require('./src/features/arena/WildTypeChallenge.js')
const {matchingWildType,wildTypeChallenge}=require('./src/features/arena/wildtype.js')
const {DevelopersFeature}=require('./src/features/developers/DevelopersFeature.js')
const {I18nProvider,Preferences}=require('./src/shared/i18n.js')
const dom=new JSDOM('<!doctype html><html><body><main id="root"></main></body></html>',{url:'http://arena.example/'})
const originals=Object.fromEntries(['window','document','navigator','localStorage','location','history','sessionStorage','requestAnimationFrame','cancelAnimationFrame','matchMedia','IS_REACT_ACT_ENVIRONMENT','fetch'].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
for(const k of ['window','document','navigator','localStorage','location','history','sessionStorage'])Object.defineProperty(globalThis,k,{configurable:true,value:dom.window[k]})
globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}})
globalThis.IS_REACT_ACT_ENVIRONMENT=true
globalThis.requestAnimationFrame=()=>1
globalThis.cancelAnimationFrame=()=>{}
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
 assert.match(document.body.textContent,/selected brain model/)
 const language=document.querySelector('select[aria-label="Language"]')
 await act(async()=>{language.value='zh-CN';language.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(document.body.textContent,/自定义算法/)
})

test('public gallery exposes real generations and branches without starting compute',async()=>{
 const {TrainingShowcase}=require('./src/features/training/TrainingShowcase.js')
 const requests=[];const branched=[]
 const fly={...own,report:{budget_used:1},spec:{...spec,weight_mutations:[{selector:'olfactory',scale:1.1}]}}
 const run={id:'c'.repeat(32),status:'complete',spec:{name:'Real CEM',strategy:'cross_entropy',founder_id:wt.id,opponent_id:null,map_id:'orchard',mode:'forage',seed:42,duration_seconds:1,population:2,generations:2,max_evaluations:4,circuits:['olfactory'],mutation_strength:.08},baseline_fitness:0,evaluation_context:'runtime',evaluations_completed:4,evaluations_started:4,evaluations_total:4,best_fly_id:fly.id,members:[{generation:0,slot:0,fitness:0,fly_id:wt.id,fly:{...fly,id:wt.id},matches:[],condition_results:[]},{generation:1,slot:1,fitness:.25,fly_id:fly.id,fly,matches:[],condition_results:[]}]}
 const older={...run,id:'e'.repeat(32),spec:{...run.spec,name:'Older run'}}
 history.replaceState(null,'','#tab=train&showcase='+run.id)
 globalThis.fetch=async(url,options)=>{requests.push([url,options?.method||'GET']);return {ok:true,json:async()=>[older,run]}}
 await mount(TrainingShowcase,{maps:[],onReplay:noop,onBranch:(f,spec,runId)=>branched.push({...f,runId}),copyAvailable:true})
 assert.equal(requests.length,1);assert.match(String(requests[0][0]),/training-showcase/)
 assert.equal(document.querySelector('.showcase-actions strong').textContent,'Real CEM')
 const olderTab=[...document.querySelectorAll('.evolution-showcase .training-tabs button')].find(b=>b.textContent.startsWith('Older run'))
 await act(async()=>olderTab.click());assert.equal(new URLSearchParams(location.hash.slice(1)).get('showcase'),older.id)
 history.replaceState(null,'','#tab=train&showcase='+run.id)
 await act(async()=>window.dispatchEvent(new dom.window.PopStateEvent('popstate')))
 assert.equal(document.querySelector('.showcase-actions strong').textContent,'Real CEM')
 await click('G21 evaluated')
 assert.match(document.body.textContent,/0.250/)
 await click('Save a copy and prepare training');assert.equal(branched[0].id,fly.id);assert.equal(branched[0].runId,run.id)
 assert.deepEqual(requests.map(r=>r[1]),['GET'])
 globalThis.fetch=()=>{throw Error('Unexpected network')}
})

test('experiment guide opens recorded candidate and baseline, explains inputs and leaves missing data unknown',async()=>{
 const {ExperimentGuide}=require('./src/features/training/ExperimentGuide.js')
 const opened=[]
 const match=(id,flyId,status='verified')=>({id,status,request:{fly_ids:[flyId]}})
 const run={best_fly_id:own.id,spec:{strategy:'evolution',map_id:'orchard',seed:42,duration_seconds:10,bridge_profile:'sensorimotor-research-v2',sensory_profile:'odor-only-v1'},members:[
  {generation:0,slot:0,fly_id:wt.id,fly:wt,matches:[match('baseline',wt.id)]},
  {generation:1,slot:1,fly_id:own.id,fly:own,matches:[match('wrong-individual',wt.id),match('unfinished',own.id,'running'),match('best',own.id)]},
 ]}
 await mount(ExperimentGuide,{run,maps:[],onReplay:m=>opened.push(m.id)})
 assert.match(document.body.textContent,/vision and touch are environment observations only/)
 assert.match(document.body.textContent,/Kernel readout and motor transfer/)
 assert.match(document.body.textContent,/seed 42 · 10 s/)
 await click('Watch best individual →');await click('Watch experiment baseline →')
 assert.deepEqual(opened,['best','baseline'])
 const language=document.querySelector('select[aria-label="Language"]')
 await act(async()=>{language.value='zh-CN';language.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(document.body.textContent,/视觉和触觉仅作环境观察/)
 await mount(ExperimentGuide,{run:{...run,spec:{...run.spec,sensory_profile:'engineered-contact-support-v1',bridge_profile:'legacy-v1'}},maps:[],onReplay:noop})
 assert.match(document.body.textContent,/味觉和左右触觉输入大脑/)
 await mount(ExperimentGuide,{run:{...run,spec:{...run.spec,sensory_profile:undefined,bridge_profile:undefined},members:[]},maps:[],onReplay:noop})
 assert.match(document.body.textContent,/感觉输入说明不可用/)
 assert.equal(button('观看最佳个体 →').disabled,true)
 assert.equal(button('观看实验基线 →').disabled,true)
 assert.ok(!document.body.textContent.includes('malecns-lif-cpu-v1'))
})

test('life record inspects a zero result, prepares branches and appends corrections without compute',async()=>{
 const {LifeLedger}=require('./src/features/life/LifeLedger.js')
 history.replaceState(null,'','#tab=life&fly='+own.id)
 const requests=[],branches=[],contests=[],replays=[]
 const match={id:'c'.repeat(32),status:'verified',request:{map_id:'orchard',mode:'forage',seed:42,duration_seconds:1,fly_ids:[own.id]}}
 const record={fly:own,can_annotate:true,origin:{strategy:'random_search',round:3,fitness:0,saved:false},ancestors:[wt],descendants:[],notes:[],experiences:[{match,scores:[0],slots:[0],evaluation_context:'runtime'}],learning:{within_match_plasticity:'none',acquired_state_inherited:false}}
 globalThis.fetch=async(url,options)=>{
  const method=options?.method||'GET';requests.push([String(url),method])
  let result
  if(method==='POST'){
   assert.ok(String(url).endsWith('/notes'));assert.ok(options.headers['Idempotency-Key'])
   const note=JSON.parse(options.body);record.notes.push({...note,id:String(record.notes.length+1).repeat(32),created:1});result={id:record.notes.at(-1).id}
  }else if(String(url).includes('/experiences/'))result={status:'recorded',observations:[{slot:0,food_consumed:0,sampled_path_mm:14.91,final_energy:98.44,total_spikes:1960853,first_intake_record_seconds:null,exit_seconds:null,final_neural_activity:{descending:12}}]}
  else result=String(url).endsWith('/lives')?[{...own,can_annotate:true}]:structuredClone(record)
  return {ok:true,json:async()=>result}
 }
 await mount(LifeLedger,{identity:{id:'owner',token:'test'},selected:own.id,onBranch:f=>branches.push(f),onCompete:f=>contests.push(f),onReplay:m=>replays.push(m)})
 assert.match(document.body.textContent,/Search round 3/)
 assert.match(document.body.textContent,/Score 0.0000/)
 assert.match(document.body.textContent,/No food consumed during this evaluation window/)
 await click('Inspect recorded observations');assert.match(document.body.textContent,/14.91 mm/)
 await click('Behavior and neural replay');assert.equal(replays[0].id,match.id)
 await click('Continue evolution');await click('Prepare a comparison')
 assert.equal(branches[0].id,own.id);assert.equal(contests[0].id,own.id)
 assert.ok(requests.every(([,m])=>m==='GET'))
 // React loaded before JSDOM uses its change-event fallback; invoke its actual handler.
 async function explain(value){await act(async()=>{const area=document.querySelector('textarea');const props=Object.keys(area).find(k=>k.startsWith('__reactProps'));area[props].onChange({target:{value}})})}
 await explain('Test a longer window');await click('Append to life record')
 assert.match(document.body.textContent,/Test a longer window/)
 const selects=document.querySelectorAll('.life-notes select')
 await act(async()=>{selects[0].value='correction';selects[0].dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 const earlier=document.querySelectorAll('.life-notes select')[2]
 await act(async()=>{earlier.value=record.notes[0].id;earlier.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 await explain('Test multiple seeds too');await click('Append to life record')
 assert.equal(record.notes.length,2);assert.equal(record.notes[1].supersedes,record.notes[0].id)
 assert.match(document.body.textContent,/Test a longer window/);assert.match(document.body.textContent,/Test multiple seeds too/)
 assert.equal(requests.filter(([,m])=>m==='POST').length,2)
 history.replaceState(null,'','/')
})

test('brain dynamics can be selected independently of optimizer without computation',async()=>{
 const {BrainModelPicker,RATE,LIF}=require('./src/features/design/BrainModelPicker.js')
 globalThis.fetch=()=>{throw Error('Model selection must not enqueue work')}
 const changed=[]
 await mount(BrainModelPicker,{value:LIF,onChange:id=>changed.push(id)})
 const radios=document.querySelectorAll('input[name="brain-model"]')
 await act(async()=>radios[1].click());assert.deepEqual(changed,[RATE])
 await mount(BrainModelPicker,{value:RATE,onChange:id=>changed.push(id)})
 assert.match(document.body.textContent,/frozen LIF motor decoder experimentally/)
 assert.match(document.body.textContent,/No discrete spikes/)
 const rateReference={...wt,id:'d'.repeat(32),spec:{...wt.spec,model_profile:RATE}}
 assert.equal(matchingWildType([rateReference,wt]),wt)
 assert.equal(matchingWildType([wt,rateReference],{...own,spec:{...own.spec,model_profile:RATE}}),rateReference)
})

for(const supportsSenses of [true,false])test(`training controls retain selected senses through evaluation and PK (capability=${supportsSenses})`,async()=>{
 const mapFile=path.join(out,'src/features/arena/MapPreview.js');
 require.cache[mapFile]={id:mapFile,filename:mapFile,loaded:true,exports:{MapPreview:()=>React.createElement('div',null,'Map fixture')}};
 const {TrainingSandbox}=require('./src/features/training/TrainingSandbox.js');
 const sensory='engineered-touch-response-v1';const runId='d'.repeat(32);let posted;let stored;const competitions=[];
 const participant={...own,report:{budget_used:0,budget_limit:100},spec:{...own.spec,parent_id:wt.id}};
 const priorFetch=globalThis.fetch;
 globalThis.fetch=async(url,options={})=>{
  const endpoint=String(url).replace(/^.*\/api\/v1/,'');let value;
  if(endpoint==='/training-showcase')value=[];
  else if(endpoint==='/training'&&options.method==='POST'){
   posted=JSON.parse(options.body);stored={id:runId,spec:posted,status:'complete',control:'run',error:null,members:[{generation:0,slot:0,fly_id:participant.id,saved:0,fitness:1,fly:participant,matches:[],condition_results:[]}],evaluations_total:4,evaluations_started:1,evaluations_completed:1,progress:.25,best_fly_id:participant.id,baseline_fitness:1,proposal_generation:null,open_slots:[]};value=stored;
  }else if(endpoint==='/training')value=stored?[stored]:[];
  else if(endpoint===`/training/${runId}/save`)value=participant;
  else if(endpoint===`/training/${runId}`)value=stored;
  else throw Error('Unexpected test request '+endpoint);
  return new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}});
 };
 const season={connectome:{circuits:[]},match_profiles:[{id:'legacy-v1',ready:true}],...(supportsSenses?{training_fitness_objectives:[{id:'food',name:'Food collected',ready:true},{id:'sustained-foraging-v1',name:'Sustained foraging',ready:true}],training_sensory_profiles:[{id:'odor-only-v1',name:'Bilateral odor only',ready:true},{id:sensory,name:'Experimental touch response · 8 mV',ready:true}]}:{})};
 try{
  await mount(TrainingSandbox,{flies:[participant,wt],identity:{id:'owner',token:'fixture-token'},selected:participant.id,season,maps:[],onLogin:noop,onSaved:async()=>{},onCompete:(...args)=>competitions.push(args),onReplay:noop});
  const select=document.getElementById('training-sensory-profile');assert.ok(select);
  assert.equal(select.options.length,supportsSenses?2:1);
  if(supportsSenses)await act(async()=>{select.value=sensory;select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))});
  const objective=document.getElementById('training-fitness-objective');assert.equal(objective.options.length,supportsSenses?2:1);
  if(supportsSenses)await act(async()=>{objective.value='sustained-foraging-v1';objective.dispatchEvent(new dom.window.Event('change',{bubbles:true}))});
  const duration=[...document.querySelectorAll('.training-setup label')].find(el=>el.textContent.startsWith('Seconds per evaluation')).querySelector('select');
  assert.equal(duration.value,'5');assert.match(document.querySelector('.training-workload').textContent,/Planned simulation time20 s/);
  await act(async()=>{duration.value='10';duration.dispatchEvent(new dom.window.Event('change',{bubbles:true}))});
  assert.match(document.querySelector('.training-workload').textContent,/Planned simulation time40 s/);
  assert.equal(posted,undefined,'Changing observation duration must not submit work');
  await click('Start training');
  assert.equal(posted.duration_seconds,10);
  assert.equal(posted.fitness_objective,supportsSenses?'sustained-foraging-v1':undefined);
  assert.equal(posted.sensory_profile,supportsSenses?sensory:undefined);
  await click('Compete');
  assert.equal(competitions.length,1);assert.equal(competitions[0][1].sensory_profile,supportsSenses?sensory:'odor-only-v1');
  assert.equal(competitions[0][1].bridge_profile,'legacy-v1');
 }finally{await act(async()=>root.render(null));globalThis.fetch=priorFetch}
});

for(const kernelInput of [false,true])test(`training selects and branches compatible research input (multisensory=${kernelInput})`,async()=>{
 const mapFile=path.join(out,'src/features/arena/MapPreview.js');
 require.cache[mapFile]={id:mapFile,filename:mapFile,loaded:true,exports:{MapPreview:()=>React.createElement('div')}};
 const {TrainingSandbox}=require('./src/features/training/TrainingSandbox.js');
 const priorFetch=globalThis.fetch;let posted,stored;const runId='e'.repeat(32);
 const lif={...own,report:{budget_used:0,budget_limit:100}},rate={...wt,id:'f'.repeat(32),spec:{...wt.spec,model_profile:'malecns-rate-cpu-v1'}};
 const touch='engineered-contact-support-v1',bridge='sensorimotor-research-v2',kernel='engineered-kernel-contact-v1';
 globalThis.fetch=async(url,options={})=>{
  const endpoint=String(url).replace('/api/v1','');let value;
  if(endpoint==='/training-showcase')value=[];
  else if(endpoint==='/training'&&options.method==='POST'){
   posted=JSON.parse(options.body);stored={id:runId,spec:posted,status:'complete',control:'run',members:[{generation:0,slot:0,fly_id:lif.id,saved:0,fitness:0,fly:lif,matches:[],condition_results:[]}],evaluations_total:4,evaluations_started:1,evaluations_completed:1,progress:.25,best_fly_id:lif.id,baseline_fitness:0,open_slots:[]};value=stored;
  }else if(endpoint==='/training')value=stored?[stored]:[];
  else if(endpoint===`/training/${runId}/save`)value=lif;
  else if(endpoint===`/training/${runId}`)value=stored;
  else throw Error('Unexpected test request '+endpoint);
  return new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}});
 };
 const props={flies:[lif,rate],identity:{id:'owner',token:'fixture-token'},selected:lif.id,maps:[],onLogin:noop,onSaved:async()=>{},onCompete:noop,onReplay:noop,season:{connectome:{circuits:[]},match_profiles:[{id:'legacy-v1',ready:true},{id:bridge,ready:false}],training_bridge_profiles:[{id:'legacy-v1',ready:true,models:['malecns-lif-cpu-v1','malecns-rate-cpu-v1'],sensory_profiles:['odor-only-v1',touch]},{id:bridge,ready:true,models:['malecns-lif-cpu-v1'],sensory_profiles:['odor-only-v1',...(kernelInput?[kernel]:[])]}],training_sensory_profiles:[{id:'odor-only-v1',ready:true},{id:touch,ready:true},...(kernelInput?[{id:kernel,ready:true}]:[])]}};
 const change=async(select,value)=>act(async()=>{select.value=value;select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))});
 try{
  await mount(TrainingSandbox,props);
  const selector=document.getElementById('training-bridge-profile'),sense=document.getElementById('training-sensory-profile');
  await change(sense,touch);await change(selector,bridge);
  assert.equal(sense.value,'odor-only-v1');assert.equal([...sense.options].find(o=>o.value===touch).disabled,true);
  assert.match(document.body.textContent,/Odor-only mode leaves vision and touch as observations/);assert.equal(posted,undefined);
  if(kernelInput){assert.equal([...sense.options].find(o=>o.value===kernel).disabled,false);await change(sense,kernel)}
  await click('Start training');assert.equal(posted.bridge_profile,bridge);assert.equal(posted.sensory_profile,kernelInput?kernel:'odor-only-v1');
  await change(selector,'legacy-v1');await click('Branch training from this fly');
  assert.equal(document.getElementById('training-bridge-profile').value,bridge);
  assert.equal(document.getElementById('training-sensory-profile').value,kernelInput?kernel:'odor-only-v1');
  const founder=[...document.querySelectorAll('.training-setup label')].find(el=>el.textContent.startsWith('Starting fly')).querySelector('select');
  await change(founder,rate.id);
  assert.equal(button('Start training').disabled,true);
  assert.match(document.body.textContent,/incompatible with the selected brain models/);
  await change(selector,'legacy-v1');assert.equal(button('Start training').disabled,false);
 }finally{await act(async()=>root.render(null));globalThis.fetch=priorFetch}
});

for(const capability of [true,false])test(`public specimen becomes a saved founder only after explicit copy (capability=${capability})`,async()=>{
 const mapFile=path.join(out,'src/features/arena/MapPreview.js');
 require.cache[mapFile]={id:mapFile,filename:mapFile,loaded:true,exports:{MapPreview:()=>React.createElement('div',null,'Map fixture')}};
 const {TrainingSandbox}=require('./src/features/training/TrainingSandbox.js');
 const sample={...own,id:'f'.repeat(32),report:{budget_used:1,budget_limit:100},spec:{...spec,weight_mutations:[{selector:'olfactory',scale:1.2}]}};
 const clone={...sample,id:'e'.repeat(32),owner:'owner',spec:{...sample.spec,parent_id:sample.id}};
 const plan={name:'Published evolution',strategy:'evolution',founder_id:wt.id,opponent_id:null,map_id:'enclosure',mode:'forage',seed:91,duration_seconds:3,population:2,generations:2,max_evaluations:4,circuits:['olfactory'],mutation_strength:.08,bridge_profile:'legacy-v1',sensory_profile:'engineered-touch-response-v1'};
 const run={id:'c'.repeat(32),status:'complete',spec:plan,baseline_fitness:1,evaluation_context:'runtime',evaluations_completed:4,evaluations_started:4,evaluations_total:4,best_fly_id:sample.id,members:[{generation:0,slot:0,fitness:1,fly_id:sample.id,fly:sample,matches:[],condition_results:[]}]};
 const requests=[],saved=[];let posted;let logins=0;
 const previousRAF=globalThis.requestAnimationFrame;globalThis.requestAnimationFrame=()=>0;
 history.replaceState(null,'','#tab=train&showcase='+run.id);
 globalThis.fetch=async(url,options={})=>{
  const endpoint=String(url).replace(/^.*\/api\/v1/,'');const method=options.method||'GET';requests.push({endpoint,method});let value;
  if(endpoint==='/training-showcase')value=[run];
  else if(endpoint===`/training-showcase/${run.id}/flies/${sample.id}/copy`){assert.equal(method,'POST');value=clone}
  else if(endpoint==='/training'&&method==='POST'){posted=JSON.parse(options.body);value={...run,id:'d'.repeat(32),spec:posted,status:'queued',members:[],open_slots:[]}}
  else if(endpoint==='/training')value=[];
  else throw Error('Unexpected request '+endpoint);
  return new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}});
 };
 const props={flies:[wt],identity:null,selected:wt.id,season:{gallery_copy_available:capability,connectome:{circuits:[]},match_profiles:[{id:'legacy-v1',ready:true}],training_sensory_profiles:[{id:'odor-only-v1',name:'Odor',ready:true},{id:plan.sensory_profile,name:'Touch',ready:true}]},maps:[{id:'orchard',english:'Orchard'},{id:'enclosure',english:'Enclosure'}],onLogin:()=>logins++,onSaved:async f=>saved.push(f),onCompete:noop,onReplay:noop};
 try{
  await mount(TrainingSandbox,props);
  assert.equal(button('Save a copy and prepare training').disabled,!capability);
  if(!capability){assert.match(document.body.textContent,/Saving a copy is not available yet/);assert.ok(requests.every(r=>r.method==='GET'));return}
  await click('Save a copy and prepare training');assert.equal(logins,1);assert.equal(saved.length,0);
  assert.ok(requests.every(r=>r.method==='GET'));
  await mount(TrainingSandbox,{...props,identity:{id:'owner',token:'fixture-token'}});
  await click('Save a copy and prepare training');
  assert.equal(saved[0].id,clone.id);assert.equal(saved[0].spec.parent_id,sample.id);
  assert.equal(requests.filter(r=>r.method==='POST').length,1);
  assert.equal(document.getElementById('training-sensory-profile').value,plan.sensory_profile);
  assert.match(document.body.textContent,/Copy saved with its public parent/);
  await click('Start training');
  assert.equal(posted.founder_id,clone.id);assert.equal(posted.map_id,plan.map_id);
  assert.equal(posted.seed,plan.seed);assert.equal(posted.duration_seconds,plan.duration_seconds);
  assert.equal(posted.sensory_profile,plan.sensory_profile);
 }finally{await act(async()=>root.render(null));globalThis.requestAnimationFrame=previousRAF;history.replaceState(null,'','/')}
});

test('portable life record links back to its public trajectory before training or competition',async()=>{
 const {LifeLedger}=require('./src/features/life/LifeLedger.js');
 const publicId='f'.repeat(32);const runId='c'.repeat(32);const actions=[];
 history.replaceState(null,'','#tab=life&fly='+publicId);
 const record={fly:{...own,id:publicId,source:{kind:'published-training',run_id:runId}},can_annotate:false,origin:null,ancestors:[],descendants:[],notes:[],experiences:[],learning:{within_match_plasticity:'none',acquired_state_inherited:false}};
 globalThis.fetch=async url=>({ok:true,json:async()=>String(url).endsWith('/lives')?[]:record});
 await mount(LifeLedger,{identity:null,selected:publicId,onBranch:()=>actions.push('branch'),onCompete:()=>actions.push('compete'),onReplay:noop});
 assert.ok(document.querySelector(`.life-actions a[href="#tab=train&showcase=${runId}"]`));
 assert.ok(![...document.querySelectorAll('.life-actions button')].some(b=>/Continue evolution|Prepare a comparison/.test(b.textContent)));
 assert.deepEqual(actions,[]);history.replaceState(null,'','/');
});

test('a food event compares recorded taste and bilateral motor response at the selected delay',async()=>{
 const {MatchObservations}=require('./src/features/arena/MatchObservations.js');
 const subject={...own,report:{budget_used:0,budget_limit:100}};const seeks=[];
 const frame=(time,taste,drives)=>({time,tick:Math.round(time*10000),poses:[],positions:[[0,0,1]],drives:[drives],traces:[{olfactory:1}],senses:[{odor:[.2,.2],visual:[0,0],touch:time>.61?1:0,contact_food:time>.61?['food-0']:[],nearest_food:1,mouth_distance:1,contact_activity:{taste,touch_left:0,touch_right:null}}]});
 const frames=[frame(.6,0,[.8,1]),frame(.61,0,[.7664,.9986]),frame(.62,0,[.7555,1.0247]),frame(.71,15.872,[.3797,.6754])];
 globalThis.fetch=async()=>({ok:true,json:async()=>({neurons:[],edges:[]})});
 await mount(MatchObservations,{scene:{flies:[subject]},frame:frames[0],frames,events:[{type:'food_contact',tick:6100,slot:0,food:['food-0']}],flies:[subject],selectedId:subject.id,season:{connectome:{circuits:[]}},onSeek:time=>seeks.push(time)});
 await click('0.61sFood contact');
 assert.equal(seeks.at(-1),.71);
 let text=document.querySelector('.event-sensor-delta').textContent;
 assert.match(text,/Food taste 0\.000 → 15\.872/);
 assert.match(text,/Left environmental touch 0\.000 → 0\.000/);
 assert.match(text,/Right environmental touch — → —/);
 assert.match(text,/Left \/ right motor drive 0\.766 \/ 0\.999 → 0\.380 \/ 0\.675/);
 const delay=document.querySelector('select[aria-label="Response observation window"]');
 await act(async()=>{delay.value='0';delay.dispatchEvent(new dom.window.Event('change',{bubbles:true}))});
 assert.equal(seeks.at(-1),.62);
 text=document.querySelector('.event-sensor-delta').textContent;assert.match(text,/Food taste 0\.000 → 0\.000/);
 assert.match(text,/0\.755 \/ 1\.025/);
});

const {ResponseStory}=require('./src/features/arena/ResponseStory.js')
test('contact response story seeks the shared body/brain clock and retains missing measurements',async()=>{
 const frames=[0,.95,1,1.2,2].map((time,i)=>({time,tick:Math.round(time*10000),poses:[],positions:[[i,0,0]],scores:[i/10],drives:[[.2,.4]],traces:[{descending:8}],senses:[{taste:i===2?1:0,touch_left:0,touch_right:0,contact_activity:{taste:i===3?16:0,touch_left:null,touch_right:0}}]}))
 const seeks=[];const props={frames,events:[{type:'food_contact',slot:0,tick:9500,food:['food-0']},{type:'food_contact',slot:1,tick:12000,food:['other']}],slot:0,time:1.2,onSeek:value=>seeks.push(value),physicsDt:.0001,inputInterval:.01}
 await mount(ResponseStory,props)
 const select=document.querySelector('select[aria-label="Observation window"]')
 assert.equal(select.options.length,2)
 assert.match(document.querySelector('[data-signal-row="activity"]').textContent,/Taste 16.00Left touch —Right touch 0.00/)
 assert.match(document.body.textContent,/10 ms block start/)
 await act(async()=>{select.value=select.options[1].value;select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.ok(Math.abs(seeks.at(-1)-.95)<1e-10)
 const svg=document.querySelector('[data-signal-row="activity"] svg')
 svg.getBoundingClientRect=()=>({left:100,width:600})
 await act(async()=>svg.dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true,clientX:400})))
 assert.ok(Math.abs(seeks.at(-1)-1.25)<1e-10)
 assert.equal(document.querySelector('[data-signal-row="activity"] svg path:nth-of-type(2)').getAttribute('d').trim(),'')
 await mount(ResponseStory,{...props,inputInterval:null,physicsDt:null})
 assert.match(document.body.textContent,/Input timing is unavailable/)
 assert.equal(document.querySelector('select[aria-label="Observation window"]').options.length,1)
})

const {LocalBrainGraph}=require('./src/features/arena/LocalBrainGraph.js')
const connectedGraph={neurons:[{id:'a',class:'input',type:'A',nt:'acetylcholine'},{id:'b',class:'projection',type:'B'},{id:'c',class:'other',type:'C',nt:'unknown'}],edges:[{edge:42,pre:'a',post:'b',count:20,baseline_weight:5.5,multiplier:1.2,weight:6.6},{edge:43,pre:'c',post:'a',count:8,baseline_weight:0,multiplier:1.5,weight:0},{edge:44,pre:'a',post:'a',count:2,baseline_weight:.55,multiplier:1,weight:.55}]}
test('local brain exposes real directions and edited weights without inventing neighbor activity',async()=>{
 const props={graph:connectedGraph,activity:new Map([['a',0],['b',9]]),scale:20,selectedClass:'input'}
 await mount(LocalBrainGraph,props)
 assert.equal(document.querySelectorAll('[data-neuron]').length,3)
 assert.equal(document.querySelector('[data-neuron="a"]').getAttribute('data-recorded'),'true')
 assert.equal(document.querySelector('[data-neuron="c"]').getAttribute('data-recorded'),'false')
 assert.equal(document.querySelector('[data-edge="42"]').getAttribute('data-edited'),'true')
 assert.match(document.querySelector('.local-brain-edge-details').textContent,/20.*5.5000.*×1.2000.*6.6000/)
 await act(async()=>document.querySelector('[data-neuron="c"]').dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true})))
 assert.match(document.querySelector('.local-brain-node-details').textContent,/Not recorded/)
 assert.match(document.querySelector('.local-brain-edge-details').textContent,/8.*0.0000.*×1.5000.*0.0000/)
 const select=document.querySelector('select[aria-label="Focus neuron"]')
 await act(async()=>{select.value='b';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(document.querySelector('.local-brain-node-details').textContent,/9.00 Hz/)
 await mount(LocalBrainGraph,{...props,activity:new Map([['a',0],['b',18]])})
 assert.match(document.querySelector('.local-brain-node-details').textContent,/18.00 Hz/)
 assert.equal(document.querySelector('select[aria-label="Focus neuron"]').value,'b')
 await mount(LocalBrainGraph,{...props,graph:{...connectedGraph,edges:[{edge:42,pre:'a',post:'b',count:20}]}})
 assert.match(document.body.textContent,/did not provide per-edge weights/)
 assert.match(document.querySelector('.local-brain-edge-details').textContent,/×—/)
})

test('replay uses its own compiled brain neighborhood and rejects a different artifact snapshot',async()=>{
 const {MatchObservations}=require('./src/features/arena/MatchObservations.js');const requests=[]
 const subject={...own,artifact_id:'compiled-design',report:{budget_used:0,budget_limit:100},brain_graph:{schema:'brain-neighborhood/v1',artifact_id:'compiled-design',connectome_sha256:spec.connectome_sha256,circuits:{olfactory:connectedGraph}}}
 const frame={time:1,tick:10000,poses:[],positions:[[0,0,1]],traces:[{olfactory:2}],brain:[{circuits:{olfactory:2},sampled_nodes:[{id:'a',activity:12}]}]}
 const props={scene:{flies:[subject]},frame,frames:[frame],events:[],flies:[],selectedId:subject.id,season:{connectome:{circuits:[]}},match:{id:'m',request:{fly_ids:[subject.id],map_id:'enclosure',mode:'forage',seed:42,duration_seconds:1},participants:[subject],result:null},onSeek:noop}
 globalThis.fetch=async url=>{requests.push(String(url));return {ok:true,json:async()=>({neurons:[],edges:[]})}}
 await mount(MatchObservations,props)
 await click('Local graph')
 assert.ok(document.querySelector('[data-edge="42"]'))
 assert.equal(requests.filter(url=>url.includes('/connectome/neurons')).length,0)
 const focus=document.querySelector('select[aria-label="Focus neuron"]')
 await act(async()=>{focus.value='c';focus.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 await mount(MatchObservations,{...props,match:JSON.parse(JSON.stringify(props.match))})
 assert.equal(document.querySelector('select[aria-label="Focus neuron"]').value,'c')
 assert.equal(requests.filter(url=>url.includes('/connectome/neurons')).length,0)
 const wrong={...subject,brain_graph:{...subject.brain_graph,artifact_id:'another-design'}}
 await mount(MatchObservations,{...props,match:{...props.match,participants:[wrong]}})
 assert.ok(requests.some(url=>url.includes('/connectome/neurons')))
 assert.ok(!document.querySelector('[data-edge="42"]'))
})

const {SharedResources}=require('./src/features/arena/SharedResources.js')
test('shared food panel keeps both identities and seeks intake/depletion on the body clock',async()=>{
 const scene={flies:[{id:'aaaaaaaa',name:'Same name',color:'mint'},{id:'bbbbbbbb',name:'Same name',color:'amber'}],food:[{id:'food-0',initial:2}]}
 const frames=[{time:0,food:[2],scores:[0,0]},{time:.03,food:[1.75],scores:[.25,0]},{time:.11,food:[0],scores:[1.5,.5]},{time:.2,food:[0],scores:[1.5,.5]}]
 const seeks=[];const props={scene,frames,frame:frames[1],onSeek:time=>seeks.push(time)}
 await mount(SharedResources,props)
 assert.match(document.querySelector('.shared-resource-totals').textContent,/1.750/)
 assert.match(document.querySelector('.shared-resource-totals').textContent,/0.250.*aaaaaaaa.*0.000.*bbbbbbbb/)
 assert.equal(document.querySelector('.shared-resource-allocation').children.length,3)
 const moments=[...document.querySelectorAll('.shared-resource-moments button')]
 await act(async()=>moments[0].click());assert.equal(seeks.at(-1),.03)
 await act(async()=>moments[1].click());assert.equal(seeks.at(-1),.11)
 await act(async()=>moments[2].click());assert.equal(seeks.at(-1),.11)
 const svg=document.querySelector('.shared-resource-timeline');svg.getBoundingClientRect=()=>({left:0,width:600})
 await act(async()=>svg.dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true,clientX:300})));assert.equal(seeks.at(-1),.1)
 await mount(SharedResources,{...props,frame:{time:.05,scores:[.25]}})
 assert.ok(!document.querySelector('.shared-resource-allocation'))
 assert.match(document.querySelector('.shared-resource-totals').textContent,/Remaining in arena—/)
 assert.match(document.querySelector('.shared-resource-totals').textContent,/Same name—.*bbbbbbbb/)
})

test('per-patch intake follows replay time and selecting an opponent meal follows that fly',async()=>{
 const scene={flies:[{id:'a',name:'Alpha',color:'mint'},{id:'b',name:'Beta',color:'amber'}],food:[{id:'food-0',initial:2},{id:'food-1',initial:2}]}
 const frames=[{tick:0,time:0,food:[2,2],scores:[0,0]},{tick:10000,time:1,food:[1,2],scores:[1,0]},{tick:20000,time:2,food:[.5,2],scores:[1,.5]},{tick:30000,time:3,food:[.5,1],scores:[2,.5]}]
 const events=[{type:'intake',tick:25000,slot:0,food:1,amount:1},{type:'intake',tick:15000,slot:1,food:0,amount:.5},{type:'intake',tick:10000,slot:0,food:0,amount:1}]
 const actions=[],props={scene,frames,events,frame:frames[1],onSeek:t=>actions.push(['seek',t]),onObserveSlot:s=>actions.push(['observe',s])}
 const row=id=>document.querySelector(`[data-food-shares="${id}"]`)
 await mount(SharedResources,props)
 assert.match(row('food-0').textContent,/1\.000.*0\.000/)
 assert.ok(!row('food-0').textContent.includes('Both have fed'))
 assert.equal(row('food-0').querySelectorAll('button')[1].disabled,true)
 assert.match(row('food-1').textContent,/0\.000.*0\.000/,'future meals stay out of current allocation')
 await mount(SharedResources,{...props,frame:frames[2]})
 assert.match(row('food-0').textContent,/Both have fed here/)
 await act(async()=>row('food-0').querySelectorAll('button')[1].click())
 assert.deepEqual(actions,[['observe',1],['seek',2]],'select the actual contestant and first recorded frame after its intake')
 await mount(SharedResources,{...props,frame:frames[3]})
 assert.match(row('food-1').textContent,/1\.000.*0\.000/)
 await mount(SharedResources,{...props,events:events.slice(1)})
 assert.match(document.querySelector('.shared-food-table').textContent,/Complete per-patch intake events are unavailable/)
 assert.ok([...row('food-0').querySelectorAll('button')].every(b=>b.disabled&&b.textContent==='—'))
 await mount(SharedResources,{...props,events:events.map(e=>({...e,food:undefined}))})
 assert.ok([...row('food-0').querySelectorAll('button')].every(b=>b.textContent==='—'))
})

test('observing the opponent switches body and brain together without changing the design selection',async()=>{
 const canvasFile=require.resolve('./src/ArenaCanvas.js')
 require.cache[canvasFile]={id:canvasFile,filename:canvasFile,loaded:true,exports:{ArenaCanvas:props=>React.createElement('div',{'data-observed-body':props.selectedId,'data-following':String(props.followSelected)})}}
 delete require.cache[require.resolve('./src/features/arena/ArenaFeature.js')]
 const {ArenaFeature}=require('./src/features/arena/ArenaFeature.js')
 const designs=[];const scene={flies:[own,wt],food:[{id:'food-0',initial:2}],body:{geoms:[]}}
 const frame={time:0,tick:0,poses:[],positions:[[0,0,1],[1,0,1]],scores:[0,0],food:[2],traces:[{},{}]}
 const props={scene,frame,next:frame,alpha:0,focused:'match',preview:null,selectedFly:own,chosenMap:null,current:{id:'match',request:{fly_ids:[own.id,wt.id],map_id:'scarcity',mode:'contest',seed:42,duration_seconds:4},result:null,participants:[own,wt]},selected:own.id,identity:null,flies:[own,wt],frames:[frame],events:[],play:false,playtime:0,playbackSpeed:1,season:{connectome:{circuits:[]}},matches:[],maps:[],mapId:'scarcity',mode:'contest',opponent:wt.id,duration:4,seed:42,busy:'',bridgeProfile:'legacy-v1',sensoryProfile:'engineered-contact-context-v1',replayStatus:'ready',replayError:'',setSelected:id=>designs.push(id)}
 for(const key of ['setSensoryProfile','setBridgeProfile','setPlay','setPlaytime','setPlaybackSpeed','setFocused','setMapId','setMode','setOpponent','setDuration','setSeed','startMatch','startSeries'])props[key]=noop
 globalThis.fetch=async()=>({ok:true,json:async()=>({neurons:[],edges:[]})})
 await mount(ArenaFeature,props)
 assert.equal(document.querySelector('[data-observed-body]').getAttribute('data-observed-body'),own.id)
 assert.equal(document.querySelector('[data-observed-body]').getAttribute('data-following'),'false')
 await click('Follow observed fly')
 assert.equal(document.querySelector('[data-observed-body]').getAttribute('data-following'),'true')
 const opponent=[...document.querySelectorAll('.observation-subjects button')].find(b=>b.textContent.includes(wt.name))
 await act(async()=>opponent.click())
 assert.equal(document.querySelector('[data-observed-body]').getAttribute('data-observed-body'),wt.id)
 assert.match(document.querySelector('.observation-participant-heading').textContent,/Canonical reference/)
 assert.deepEqual(designs,[])
 assert.match(document.querySelector('.score-overlay .selected-subject').textContent,/Canonical reference/)
 assert.equal(document.querySelector('[data-observed-body]').getAttribute('data-following'),'true')
 await click('Arena overview')
 assert.equal(document.querySelector('[data-observed-body]').getAttribute('data-following'),'false')
})

const {NeuralPreviewPanel}=require('./src/features/design/NeuralPreviewPanel.js')

test('replay drafts retain full neural edits and parent identity without altering recorded designs',async()=>{
 const {draftFromReplay}=require('./src/features/arena/replayDesign.js')
 const {ReplayDesignActions}=require('./src/features/arena/ReplayDesignActions.js')
 const participant={...own,spec:{...spec,name:'x'.repeat(64),parent_id:wt.id,weight_mutations:[{selector:'olfactory',scale:1.18}],edge_deltas:[{edge:17,log_delta:.05}],interventions:[{selector:{pre:{ids:['10001']}},scale:1.1}],future_field:{value:3}}}
 const before=structuredClone(participant),calls=[]
 const draft=draftFromReplay(participant)
 assert.equal(draft.parent_id,participant.id);assert.equal(draft.name.length,64)
 assert.deepEqual(draft.edge_deltas,participant.spec.edge_deltas)
 assert.deepEqual(draft.interventions,participant.spec.interventions)
 assert.deepEqual(draft.future_field,{value:3})
 draft.interventions[0].selector.pre.ids.push('edited');assert.deepEqual(participant,before)
 globalThis.fetch=()=>{throw Error('Opening a replay draft must not request compute')}
 await mount(ReplayDesignActions,{participant,matchId:'recorded-match',onDesign:(...args)=>calls.push(args)})
 await click('Design from this brain')
 assert.equal(calls[0][0].parent_id,participant.id)
 assert.deepEqual(calls[0][1],{matchId:'recorded-match',flyId:participant.id,name:participant.name})
 assert.deepEqual(participant,before)
 await mount(ReplayDesignActions,{matchId:'missing',onDesign:noop})
 assert.match(document.body.textContent,/no usable participant design snapshot/)
 assert.ok(![...document.querySelectorAll('button')].some(b=>b.textContent.includes('Design from this brain')))
})

test('downloaded AI draft is the editable child FlySpec and contains no match or account wrapper',async()=>{
 const {ReplayDesignActions}=require('./src/features/arena/ReplayDesignActions.js')
 const originalCreate=URL.createObjectURL,originalRevoke=URL.revokeObjectURL,originalClick=dom.window.HTMLAnchorElement.prototype.click
 let blob,filename
 URL.createObjectURL=value=>{blob=value;return 'blob:replay-draft'};URL.revokeObjectURL=()=>{}
 dom.window.HTMLAnchorElement.prototype.click=function(){filename=this.download}
 try{
  await mount(ReplayDesignActions,{participant:own,matchId:'source-match',onDesign:noop})
  await click('Download draft for AI')
  const exported=JSON.parse(await blob.text())
  assert.equal(exported.schema_version,'flyspec/v1');assert.equal(exported.parent_id,own.id)
  assert.deepEqual(exported.weight_mutations,spec.weight_mutations)
  assert.equal(exported.owner,undefined);assert.equal(exported.match,undefined)
  assert.equal(filename,`fly-${own.id}-child.flyspec.json`)
 }finally{URL.createObjectURL=originalCreate;URL.revokeObjectURL=originalRevoke;dom.window.HTMLAnchorElement.prototype.click=originalClick}
})

test('a replay participant becomes an editable saved child and the exact new training founder',async()=>{
 const canvasFile=require.resolve('./src/ArenaCanvas.js')
 require.cache[canvasFile]={id:canvasFile,filename:canvasFile,loaded:true,exports:{ArenaCanvas:()=>React.createElement('div',null,'Recorded body fixture')}}
 const mapFile=require.resolve('./src/features/arena/MapPreview.js')
 require.cache[mapFile]={id:mapFile,filename:mapFile,loaded:true,exports:{MapPreview:()=>React.createElement('div',null,'Map fixture')}}
 const participant={...own,color:'mint',artifact_id:'recorded-artifact',spec:{...spec,name:'Recorded brain',weight_mutations:[{selector:'olfactory',scale:1.18}],edge_deltas:[{edge:17,log_delta:.05}]},report:{budget_used:12,budget_limit:100}}
 const scene={flies:[participant],food:[],body:{geoms:[]}},frame={time:0,tick:0,poses:[],positions:[[0,0,1]],scores:[0],traces:[{}]}
 const replayFile=require.resolve('./src/features/arena/useReplay.js')
 require.cache[replayFile]={id:replayFile,filename:replayFile,loaded:true,exports:{useReplay:()=>({scene,frames:[frame],events:[],status:'ready',error:''})}}
 const match={id:'replay-match',status:'verified',request:{fly_ids:[own.id],map_id:'orchard',mode:'forage',seed:42,duration_seconds:30},result:{scores:[1],winner_slot:null,outcome:'solo'},participants:[participant]}
 const owner={id:'viewer',name:'Viewer',token:'test-token'},writes=[],library=[{...participant,owner:'other',designer:'Other'}]
 localStorage.setItem('flyarena.identity',JSON.stringify(owner))
 history.replaceState(null,'','#tab=arena&match=replay-match')
 const season={connectome:{sha256:spec.connectome_sha256,neuron_count:100,edge_count:1000,circuits:[{id:'olfactory',label:'Olfactory',edge_count:100,color:'#91bca5'}]},budget:{points:100},default_bridge_profile:'legacy-v1',match_profiles:[{id:'legacy-v1',ready:true}]}
 globalThis.fetch=async(url,options={})=>{
  const path=String(url).replace('/api/v1','')
  if(options.method==='POST'){
   assert.equal(path,'/flies','Draft opening must not start a match or training')
   const value=JSON.parse(options.body);writes.push(value)
   const saved={...participant,id:'c'.repeat(32),owner:owner.id,name:value.name,spec:value};library.push(saved)
   return {ok:true,json:async()=>saved}
  }
  const data=path==='/auth/config'?{mode:'local'}:path==='/me'?owner:path==='/season'?season:path==='/flies'?library:path==='/maps'?[]:path==='/matches'?[match]:path==='/matches/replay-match'?match:path==='/preview'?{body:scene.body,frame}:path==='/leaderboard'||path==='/training'||path==='/training-showcase'?[]:path.includes('/receipt')?{}:{neurons:[],edges:[]}
  return {ok:true,json:async()=>data}
 }
 delete require.cache[require.resolve('./src/features/arena/ArenaFeature.js')]
 delete require.cache[require.resolve('./src/features/training/TrainingSandbox.js')]
 delete require.cache[require.resolve('./src/App.js')]
 const App=require('./src/App.js').default
 await mount(App,{})
 await click('Design from this brain')
 assert.equal(new URLSearchParams(location.hash.slice(1)).get('tab'),'design')
 assert.equal(document.getElementById('fly-name').value,'Recorded brain child')
 assert.match(document.querySelector('.draft-status').textContent,new RegExp(own.id))
 assert.match(document.querySelector('.replay-design-origin').textContent,/unsaved child draft/)
 assert.equal(document.querySelector('input[aria-label="Olfactory Weight"]').value,'1.18')
 assert.equal(writes.length,0)
 await click('Revisit the parent’s match');assert.match(location.hash,/match=replay-match/)
 await click('Design from this brain')
 const save=document.querySelector('.editor-actions .primary');assert.ok(save)
 await act(async()=>save.click())
 assert.equal(writes.length,1);assert.equal(writes[0].parent_id,own.id)
 assert.deepEqual(writes[0].edge_deltas,participant.spec.edge_deltas)
 assert.deepEqual(writes[0].weight_mutations,participant.spec.weight_mutations)
 assert.equal(new URLSearchParams(location.hash.slice(1)).get('tab'),'train')
 const founder=[...document.querySelectorAll('label')].find(label=>label.textContent.startsWith('Starting fly'))?.querySelector('select')
 assert.ok(founder);assert.equal(founder.value,'c'.repeat(32))
 assert.equal(participant.spec.parent_id,null)
})
const neuralRecord=()=>({specKey:null,data:{schema:'neural-design-preview/v2',artifact_id:'nectar-artifact',model_profile:spec.model_profile,connectome_sha256:spec.connectome_sha256,steps:1200,scope:'test data',spec:{...spec,name:'Recorded Nectar'},reference:{artifact_id:'wt-artifact',spec},protocol:{duration_ms:120,sample_interval_ms:10,onset_ms:20,offset_ms:80},example:{name:'Recorded Nectar',related_match_id:'real-match',execution:'local CPU'},stimuli:[0,1,2,3].map(trial=>({stimulus:{left:trial===0||trial===2?1:0,right:trial===1||trial===2?1:0},circuits:{projection:999,motor:999},total_spikes:100,samples:Array.from({length:13},(_,i)=>({time_ms:i*10,stimulus:{left:0,right:0},circuits:{projection:trial*100+i,motor:0},reference_circuits:{projection:i/2,motor:0},total_spikes:i,reference_total_spikes:i}))}))}})

test('stimulus preview changes paired observations with time and stimulus, and opens exact sample design',async()=>{
 const record=neuralRecord(),imports=[],replays=[]
 await mount(NeuralPreviewPanel,{record,stale:false,circuits:[],onImport:s=>imports.push(s),onReplay:id=>replays.push(id)})
 assert.match(document.body.textContent,/not the current editor draft/)
 assert.match(button('projection').textContent,/8\.00 HzWT 4\.00 HzΔ \+4\.00 Hz/)
 const select=document.querySelector('select[aria-label="Choose stimulus"]')
 await act(async()=>{select.value='1';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(button('projection').textContent,/108\.00 Hz/)
 const slider=document.querySelector('input[aria-label="Neural preview time"]')
 await act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(slider,'3');slider.dispatchEvent(new dom.window.Event('input',{bubbles:true}));slider.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(button('projection').textContent,/103\.00 Hz/)
 await click('motor');assert.match(document.querySelector('.stimulus-preview__chart').getAttribute('aria-label'),/^motor /)
 await click('Load example design into editor');await click('Watch this design in a real contest')
 assert.equal(imports[0],record.data.spec);assert.deepEqual(replays,['real-match'])
})
test('stimulus preview leaves absent sample values missing instead of borrowing the final value',async()=>{
 const record=neuralRecord();delete record.data.stimuli[0].samples[8].circuits.projection
 record.specKey='previous-submission'
 await mount(NeuralPreviewPanel,{record,stale:true,circuits:[],onImport:noop,onReplay:noop})
 assert.match(document.body.textContent,/draft has changed/)
 assert.match(button('projection').textContent,/Design — HzWT 4\.00 HzΔ —/)
 assert.doesNotMatch(button('projection').textContent,/999/)
 assert.match(button('motor').textContent,/0\.00 Hz/)
})
test('legacy neural preview announces missing paired protocol without inventing WT values',async()=>{
 const record=neuralRecord();record.specKey='submitted';delete record.data.protocol;delete record.data.reference
 for(const row of record.data.stimuli)delete row.samples
 await mount(NeuralPreviewPanel,{record,stale:false,circuits:[],onImport:noop,onReplay:noop})
 assert.match(document.body.textContent,/legacy single-time preview/)
 assert.equal(document.querySelector('input[aria-label="Neural preview time"]'),null)
 assert.match(button('projection').textContent,/WT —Δ —/)
})

test('motor commands follow preview time and stimulus while missing motor samples remain blank',async()=>{
 const record=neuralRecord();record.data.schema='neural-design-preview/v3'
 record.data.motor_readout={available:true,id:'descending-ridge-v1'}
 record.data.example.same_motor_readout_as_related_match=false
 for(const [trial,row] of record.data.stimuli.entries())for(const [i,sample] of row.samples.entries()){
  sample.motor={raw:[i/10,-.2],clipped:[i/10,0],drive:[i/100+trial/10,0]}
  sample.reference_motor={raw:[.5,.4],clipped:[.5,.4],drive:[.03,.02]}
 }
 await mount(NeuralPreviewPanel,{record,stale:false,circuits:[],onImport:noop,onReplay:noop})
 const drive=()=>document.querySelector('[data-motor-stage="drive"]').textContent
 assert.match(drive(),/0\.0800\.030/)
 assert.match(document.querySelector('[data-motor-stage="raw"]').textContent,/0\.8000\.500/)
 const slider=document.querySelector('input[aria-label="Neural preview time"]')
 await act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(slider,'3');slider.dispatchEvent(new dom.window.Event('input',{bubbles:true}))})
 assert.match(drive(),/0\.0300\.030/)
 const select=document.querySelector('select[aria-label="Choose stimulus"]')
 await act(async()=>{select.value='1';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(drive(),/0\.1300\.030/)
 record.data.stimuli[0].samples[8].motor=null
 await mount(NeuralPreviewPanel,{record:{...record},stale:false,circuits:[],onImport:noop,onReplay:noop})
 assert.match(drive(),/—0\.030/)
 assert.match(document.body.textContent,/not speeds or observed turns/)
 assert.match(document.body.textContent,/different motor decoder calibration/)
 assert.equal(document.querySelectorAll('.stimulus-preview__motor svg').length,2)
})

test('old previews explicitly omit unrecorded motor output',async()=>{
 await mount(NeuralPreviewPanel,{record:neuralRecord(),stale:false,circuits:[],onImport:noop,onReplay:noop})
 assert.match(document.body.textContent,/no available motor readout/)
 assert.equal(document.querySelector('.stimulus-preview__motor svg'),null)
})

test('paired stimulus brains share an activity scale and selecting a brain region opens its measured curve',async()=>{
 const record=neuralRecord(),circuits=['projection','motor'].map(id=>({id,label:id,name:id,color:'#98dbc0',neuron_count:10,edge_count:20}))
 await mount(NeuralPreviewPanel,{record,stale:false,circuits,onImport:noop,onReplay:noop})
 const legends=[...document.querySelectorAll('.brain-overview-legend')].map(el=>el.textContent)
 assert.equal(legends.length,2);assert.equal(legends[0],legends[1]);assert.match(legends[0],/312\.00 Hz/)
 const node=document.querySelector('.brain-overview [data-circuit="motor"]')
 await act(async()=>node.dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true})))
 assert.match(document.querySelector('.stimulus-preview__chart').getAttribute('aria-label'),/^motor /)
 assert.match(document.body.textContent,/response curve/)
 const select=document.querySelector('select[aria-label="Choose stimulus"]')
 await act(async()=>{select.value='2';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.equal(document.querySelector('.brain-overview-legend').textContent,legends[0])
})

test('contact response windows seek recorded environmental and support observations',async()=>{
 const {ResponseStory}=require('./src/features/arena/ResponseStory.js'),seeks=[]
 const frames=[{tick:0,time:0,scores:[0],senses:[{taste:0,touch_left:0,touch_right:0}]},{tick:100,time:.01,scores:[0],senses:[{taste:0,touch_left:0,touch_right:0,contact_support:['obstacle-19']}]},{tick:200,time:.02,scores:[0],senses:[{taste:0,touch_left:0,touch_right:1,contact_support:['obstacle-19']}]}]
 await mount(ResponseStory,{frames,events:[{type:'environment_contact',tick:100,slot:0,objects:['obstacle-19']}],slot:0,time:0,onSeek:t=>seeks.push(t),inputInterval:.01,physicsDt:.0001})
 const select=document.querySelector('select[aria-label="Observation window"]')
 assert.match(select.textContent,/Environment contact · 0\.01 s obstacle-19/)
 assert.equal([...select.options].filter(o=>o.text.includes('First sampled foot support')).length,1)
 await act(async()=>{select.value='.01';select.value='0.01';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.deepEqual(seeks,[.01])
})

test('feeding history seeks measured contact/intake, preserves brief intake and exposes the nonfeeding tail',async()=>{
 const {FeedingHistory}=require('./src/features/arena/FeedingHistory.js'),seeks=[]
 const events=[{type:'food_contact',tick:9400,slot:0,food:['food-0']},{type:'intake',tick:9500,slot:0,food:0,amount:.4},{type:'intake',tick:10000,slot:0,food:0,amount:.4},{type:'intake',tick:35500,slot:0,food:3,amount:.056}]
 const props={events,scene:{food:[0,1,2,3].map(i=>({id:'food-'+i}))},slot:0,endTime:30,time:1,physicsDt:.0001,accountingTicks:500,onSeek:t=>seeks.push(t)}
 await mount(FeedingHistory,props)
 assert.equal(document.querySelectorAll('.feeding-history__jump').length,2)
 assert.match(document.body.textContent,/2 food patches · 0\.856 food units/)
 assert.match(document.body.textContent,/26\.45 s without another recorded intake/)
 assert.match(document.body.textContent,/No food-contact event was recorded/)
 await act(async()=>document.querySelectorAll('.feeding-history__jump')[0].click())
 await act(async()=>document.querySelectorAll('.feeding-history__jump')[1].click())
 await act(async()=>document.querySelectorAll('.feeding-history__tail button')[1].click())
 assert.ok(Math.abs(seeks[0]-.94)<1e-12);assert.ok(Math.abs(seeks[1]-3.55)<1e-12);assert.equal(seeks[2],30)
 await mount(FeedingHistory,{...props,physicsDt:null})
 assert.match(document.body.textContent,/event clock is unavailable/)
 assert.equal(document.querySelectorAll('.feeding-history__jump').length,0)
})


test('actual replay camera follows recorded positions, retains orbit/zoom and restores the overview',async()=>{
 const THREE=require('three'),fiberFile=require.resolve('@react-three/fiber'),originalFiber=require.cache[fiberFile]
 const camera=new THREE.PerspectiveCamera();camera.position.set(17,-25,12)
 const controls={target:new THREE.Vector3(0,0,.25),update(){camera.lookAt(this.target)}}
 let tick
 require.cache[fiberFile]={id:fiberFile,filename:fiberFile,loaded:true,exports:{...require('@react-three/fiber'),useThree:()=>({camera}),useFrame:fn=>{tick=fn}}}
 delete require.cache[require.resolve('./src/features/arena/ReplayCamera.js')]
 const {ReplayCamera}=require('./src/features/arena/ReplayCamera.js')
 const props={scene:{flies:[{id:'nectar'},{id:'wt'}],habitat:'forest-floor'},frame:{positions:[[0,0,1],[7,2,1]]},next:{positions:[[2,4,3],[9,4,1]]},alpha:.5,selectedId:'nectar',follow:false,overview:[17,-25,12]}
 try{
  await mount(ReplayCamera,props);tick({controls})
  assert.deepEqual(camera.position.toArray(),[17,-25,12])
  await mount(ReplayCamera,{...props,follow:true});tick({controls})
  assert.deepEqual(controls.target.toArray(),[1,2,2]);assert.deepEqual(camera.position.toArray(),[6,-5,6])
  // Manual orbit and zoom should survive motion and arbitrary replay seeking.
  camera.position.set(11,3,8)
  await mount(ReplayCamera,{...props,follow:true,alpha:1});tick({controls})
  assert.deepEqual(controls.target.toArray(),[2,4,3]);assert.deepEqual(camera.position.toArray(),[12,5,9])
  tick({controls});assert.deepEqual(camera.position.toArray(),[12,5,9]) // Paused frame does not drift.
  await mount(ReplayCamera,{...props,follow:true,selectedId:'wt'});tick({controls})
  assert.deepEqual(controls.target.toArray(),[8,3,1]);assert.deepEqual(camera.position.toArray(),[13,-4,5])
  await mount(ReplayCamera,{...props,follow:true,selectedId:'missing'});tick({controls})
  assert.deepEqual(controls.target.toArray(),[8,3,1]) // Never silently follow a different fly.
  await mount(ReplayCamera,props);tick({controls})
  assert.deepEqual(camera.position.toArray(),[17,-25,12]);assert.deepEqual(controls.target.toArray(),[0,0,.25])
 }finally{await act(async()=>root.render(null));require.cache[fiberFile]=originalFiber}
})


test('behavior evaluation exposes food, late intake and actual posture without assigning values to missing records',async()=>{
 const {BehaviorFitness}=require('./src/features/training/BehaviorFitness.js')
 await mount(BehaviorFitness,{metric:null});assert.equal(document.querySelector('.behavior-fitness'),null)
 await mount(BehaviorFitness,{metric:{schema:'sustained-foraging-v1',food:10,latter_half_food:2,upright_fraction:.25,recorded_seconds:30,first_inversion_s:3,fitness:3}})
 assert.match(document.querySelector('.behavior-fitness summary').textContent,/3\.000/)
 assert.match(document.body.textContent,/Time not inverted25\.0%/)
 assert.match(document.body.textContent,/Food in second half2\.000/)
 assert.match(document.body.textContent,/does not change the match winner/)
})

test('lineage behavior uses each participant slot and opens actual baseline, parent and descendant replays',async()=>{
 const {LineageBehavior}=require('./src/features/training/LineageBehavior.js')
 const metric=(food)=>({schema:'sustained-foraging-v1',food,latter_half_food:food/2,upright_fraction:1,recorded_seconds:10,first_inversion_s:null,fitness:food*1.5})
 const member=(id,generation,parent,food)=>({fly_id:id,generation,slot:0,fitness:food*1.5,fly:{...own,id,name:id,spec:{...spec,parent_id:parent}},matches:[{id:'match-'+id,status:'verified',request:{map_id:'enclosure',mode:'contest',seed:42,duration_seconds:10,fly_ids:['opponent',id]},result:{behavior:[metric(900),metric(food)]}}]})
 const base=member('baseline',0,'original-founder',.5),parent=member('parent',1,base.fly_id,10),child=member('child',2,parent.fly_id,12)
 const replay=[];const run={best_fly_id:child.fly_id,members:[base,parent,child]}
 await mount(LineageBehavior,{run,onReplay:m=>replay.push(m.id)})
 const table=document.querySelector('.lineage-behavior-table')
 assert.match(table.textContent,/0\.500/);assert.match(table.textContent,/10\.000/);assert.match(table.textContent,/12\.000/)
 assert.doesNotMatch(table.textContent,/900\.000/)
 const buttons=[...table.querySelectorAll('button')]
 for(const b of buttons)await act(async()=>b.click())
 assert.deepEqual(replay,['match-baseline','match-parent','match-child'])
 assert.match(document.body.textContent,/not automatically wild type/)
 assert.match(document.body.textContent,/No circuit multiplier changes/)
 const select=document.querySelector('.lineage-behavior-heading select')
 await act(async()=>{select.value='baseline';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(document.body.textContent,/Parent evaluation not included/)
 assert.equal(document.querySelectorAll('.lineage-behavior-table button').length,2)
 const language=document.querySelector('select[aria-label="Language"]')
 await act(async()=>{language.value='zh-CN';language.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(document.body.textContent,/观看身体与大脑/)
})

test('lineage comparison keeps mismatched conditions and missing neural behavior distinct from zero',async()=>{
 const {LineageBehavior,matchedLifeReplay}=require('./src/features/training/LineageBehavior.js')
 const request={map_id:'enclosure',mode:'contest',seed:42,duration_seconds:10,bridge_profile:'sensorimotor-research-v2',sensory_profile:'engineered-contact-support-v1',fly_ids:['child','opponent']}
 const reference={id:'child-match',status:'verified',request,result:null}
 const child={fly_id:'child',generation:1,slot:0,fly:{...own,id:'child',spec:{...spec,parent_id:'baseline'}},matches:[reference]}
 const matching={id:'baseline-match',status:'verified',request:{...request,fly_ids:['baseline','opponent']},result:null}
 const base={fly_id:'baseline',generation:0,slot:0,fly:{...own,id:'baseline',spec},matches:[matching]}
 assert.equal(matchedLifeReplay(base,child,reference),matching)
 for(const change of [{seed:43},{duration_seconds:30},{map_id:'orchard'},{sensory_profile:'odor-only-v1'},{bridge_profile:'legacy-v1'},{fly_ids:['opponent','baseline']},{fly_ids:['baseline','other-opponent']}]){
  assert.equal(matchedLifeReplay({...base,matches:[{...matching,request:{...matching.request,...change}}]},child,reference),undefined)
 }
 assert.equal(matchedLifeReplay({...base,fly:{...base.fly,spec:{...spec,model_profile:'other'}}},child,reference),undefined)
 const mismatched={...base,matches:[{...matching,request:{...matching.request,seed:99}}]}
 await mount(LineageBehavior,{run:{best_fly_id:'child',members:[mismatched,child]},onReplay:noop})
 const table=document.querySelector('.lineage-behavior-table')
 assert.equal(table.querySelectorAll('button').length,1)
 assert.match(table.textContent,/No matching replay/);assert.match(table.textContent,/—/)
 assert.doesNotMatch(table.textContent,/0\.000|100\.0%|None recorded in window/)
})

test('synchronized life comparison seeks actual bodies and brains, shares scales, and rejects stale records',async()=>{
 const canvasFile=require.resolve('./src/ArenaCanvas.js'),replayFile=require.resolve('./src/features/arena/useReplay.js')
 const oldCanvas=require.cache[canvasFile],oldReplay=require.cache[replayFile]
 require.cache[canvasFile]={id:canvasFile,filename:canvasFile,loaded:true,exports:{ArenaCanvas:p=>React.createElement('div',{'data-paired-body':p.selectedId,'data-sample':p.frame?.time,'data-alpha':p.alpha})}}
 delete require.cache[replayFile];delete require.cache[require.resolve('./src/features/arena/ReplayComparison.js')]
 const {ReplayComparison,comparisonWindow,comparisonActivityScales}=require('./src/features/arena/ReplayComparison.js')
 const participant=id=>({...own,id,name:id,artifact_id:id,spec,brain_graph:{schema:'brain-neighborhood/v1',artifact_id:id,connectome_sha256:spec.connectome_sha256,circuits:{olfactory:{neurons:[],edges:[]}}}})
 const a=participant('left'),b=participant('right'),c=participant('third')
 const scene=f=>({flies:[f],size:28,food:[],obstacles:[],body:{meshes:{},geoms:[]}})
 const frames=(times,mult)=>times.map((time,i)=>({time,tick:Math.round(time*10000),poses:[],positions:[[i,0,1]],scores:[i],brain:[{circuits:{olfactory:i*mult},sampled_nodes:[{id:'n',activity:i*mult*2}]}],traces:[{olfactory:i*mult}]}))
 const left=frames([0,.05,.15,.3],2),right=frames([0,.1,.2],10)
 const match=(id,fly,seed)=>({id,status:'verified',participants:[fly],request:{fly_ids:[fly.id],map_id:'enclosure',mode:'forage',seed,duration_seconds:1}})
 const current=match('a',a,42),other=match('b',b,43),slow=match('c',c,44)
 const data={b:{scene:scene(b),frames:right,events:[]},c:{scene:scene(c),frames:right,events:[]}},pending=[],requests=[]
 globalThis.fetch=async(url,options={})=>{
  requests.push([String(url),options.method||'GET']);const parts=String(url).split('/'),kind=parts.at(-1),id=parts.at(-2)
  assert.ok(data[id]&&kind in data[id],`Unexpected request ${url}`)
  if(id==='c')await new Promise(resolve=>pending.push(resolve))
  return {ok:true,json:async()=>data[id][kind]}
 }
 try{
  const season={connectome:{circuits:[{id:'olfactory',label:'Olfactory',color:'#91bca5',neuron_count:1}]}}
  await mount(ReplayComparison,{match:current,scene:scene(a),frames:left,events:[{type:'intake',tick:500,slot:0,amount:1}],matches:[current,other,slow],season,selectedId:a.id})
  await act(async()=>{for(const button of document.querySelectorAll('.brain-layer-tabs button'))if(button.textContent==='Functional region')button.click()})
  assert.deepEqual(comparisonWindow(left,right),{start:0,end:.2});assert.equal(comparisonWindow(left,[]),null);assert.equal(comparisonWindow(left,frames([1,2],1)),null)
  assert.deepEqual(comparisonActivityScales([left,right]),{region:20,node:40})
  assert.equal(document.querySelectorAll('[data-paired-body]').length,2)
  assert.ok([...document.querySelectorAll('.brain-overview-legend')].every(e=>e.textContent.includes('0–20.00 Hz')))
  const priorRAF=globalThis.requestAnimationFrame,priorCancel=globalThis.cancelAnimationFrame
  let tick,cancelled=0
  globalThis.requestAnimationFrame=fn=>{tick=fn;return 7};globalThis.cancelAnimationFrame=()=>cancelled++
  try{
   await click('Play both replays')
   await act(async()=>tick(performance.now()+60))
   const clock=Number(document.querySelector('input[aria-label="Shared replay time"]').value)
   assert.ok(clock>0&&clock<.2)
   const samples=[...document.querySelectorAll('[data-paired-body]')]
   const selections=[left,right].map(frames=>{const i=Math.max(0,frames.findIndex(f=>f.time>clock)-1);return frames[i].time})
   assert.deepEqual(samples.map(e=>Number(e.dataset.sample)),selections)
   await click('Pause both replays');assert.ok(cancelled>0)
  }finally{globalThis.requestAnimationFrame=priorRAF;globalThis.cancelAnimationFrame=priorCancel}

  await act(async()=>document.querySelector('.life-event-rows button').click())
  const bodies=[...document.querySelectorAll('[data-paired-body]')]
  assert.equal(bodies[0].dataset.sample,'0.15');assert.equal(bodies[1].dataset.sample,'0.1');assert.ok(Math.abs(Number(bodies[1].dataset.alpha)-.5)<1e-9)
  assert.equal(document.querySelector('input[aria-label="Shared replay time"]').value,'0.15')
  assert.deepEqual([...document.querySelectorAll('.brain-overview-heading b')].map(e=>e.textContent),['0.15 s','0.10 s'])
  const pick=document.querySelector('.replay-comparison-picker select')
  await act(async()=>{pick.value='c';pick.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
  assert.equal(document.querySelectorAll('[data-paired-body]').length,0);assert.match(document.body.textContent,/Loading the other body/)
  await act(async()=>{pick.value='b';pick.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
  assert.equal(document.querySelectorAll('[data-paired-body]').length,2)
  await act(async()=>{for(const resolve of pending)resolve()})
  assert.equal(document.querySelectorAll('[data-paired-body]')[1].dataset.pairedBody,'right')
  assert.ok(requests.every(([,method])=>method==='GET'))
 }finally{await act(async()=>root.render(null));require.cache[canvasFile]=oldCanvas;require.cache[replayFile]=oldReplay}
})

test('ordinary replay loads its compiled brain and labels canonical fallback when binding fails',async()=>{
 const {BrainTheater}=require('./src/features/arena/MatchObservations.js')
 const fly={...own,artifact_id:'own-artifact',spec},requests=[]
 const canonical={neurons:connectedGraph.neurons,edges:connectedGraph.edges.map(({edge,pre,post,count})=>({edge,pre,post,count}))}
 globalThis.fetch=async(url)=>{
  requests.push(String(url));return {ok:true,json:async()=>String(url).includes('/brain/')?{schema:'brain-neighborhood/v1',artifact_id:fly.artifact_id,connectome_sha256:spec.connectome_sha256,circuits:{olfactory:connectedGraph}}:canonical}
 }
 const frame={time:0,tick:0,brain:[{circuits:{olfactory:2},sampled_nodes:[{id:'a',activity:0},{id:'b',activity:9}]}]}
 const props={matchId:'new-match',fly,frame,frames:[frame],season:{connectome:{circuits:[{id:'olfactory',label:'Olfactory',color:'#91bca5'}]}},slot:0,events:[],onSeek:noop,activityScale:20,nodeScale:20}
 await mount(BrainTheater,props);await click('Local graph')
 assert.match(document.querySelector('.local-brain-edge-details').textContent,/×1.2000.*6.6000/)
 assert.ok(requests.some(url=>url.includes('/matches/new-match/brain/0?ids=')))
 assert.ok(!requests.some(url=>url.includes('/connectome/neurons')))
 await mount(BrainTheater,{...props,fly:{...fly,artifact_id:'different-artifact'}})
 assert.match(document.body.textContent,/design weights are unavailable/)
 assert.doesNotMatch(document.querySelector('.local-brain-edge-details').textContent,/6.6000/)
 assert.ok(requests.some(url=>url.includes('/connectome/neurons')))
 globalThis.fetch=()=>{throw Error('Unexpected request')}
})

const {NeuronActivityTrace}=require('./src/features/arena/NeuronActivityTrace.js')
test('selected neuron history preserves missing samples, zero, participant identity and the body clock',async()=>{
 const seeks=[]
 const frames=[0,1,2,3,4].map((time,i)=>({time,brain:[
  {sampled_nodes:i===2?[]:[{id:'a',activity:[0,12,null,4,12][i]}]},
  {sampled_nodes:[{id:'a',activity:i===3?90:0}]}
 ]}))
 const props={neuronId:'a',frames,slot:0,time:2,onSeek:t=>seeks.push(t)}
 await mount(NeuronActivityTrace,props)
 assert.match(document.body.textContent,/4\/5 frames recorded/)
 assert.match(document.querySelector('.neuron-activity-summary').textContent,/Current sample: — · 2.00 s/)
 const d=document.querySelector('[data-neuron-trace]').getAttribute('d')
 assert.equal((d.match(/M/g)||[]).length,2,'missing samples break the curve')
 assert.match(d,/M0.00,76.00/,'recorded zero is a point, not missing')
 assert.match(document.body.textContent,/Fixed scale: 0–12.00 Hz/)
 await click('Go to recorded peak · 12.00 Hz / 1.00 s');assert.equal(seeks.at(-1),1)
 const svg=document.querySelector('.neuron-activity-trace svg')
 svg.getBoundingClientRect=()=>({left:100,width:400})
 await act(async()=>svg.dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true,clientX:410})))
 assert.equal(seeks.at(-1),3,'curve clicks seek an actual replay sample')
 await mount(NeuronActivityTrace,{...props,time:4})
 assert.match(document.body.textContent,/Fixed scale: 0–12.00 Hz/)
 assert.equal(document.querySelector('[data-neuron-cursor]').getAttribute('x1'),'600')
 await mount(NeuronActivityTrace,{...props,slot:1})
 await click('Go to recorded peak · 90.00 Hz / 3.00 s');assert.equal(seeks.at(-1),3)
 await mount(NeuronActivityTrace,{...props,neuronId:'unsampled-neighbor'})
 assert.match(document.body.textContent,/did not record this neuron/)
 assert.equal(document.querySelector('[data-neuron-trace]'),null)
 assert.equal(document.querySelector('.neuron-activity-seek'),null)
 await mount(NeuronActivityTrace,{...props,frames:[{time:1,brain:[{top_nodes:[{id:'a',activity:0}]}]}]})
 assert.match(document.body.textContent,/1\/1 frames recorded/)
 assert.equal(document.querySelector('.neuron-activity-seek input').disabled,true)
 assert.equal(document.querySelectorAll('.neuron-activity-trace circle').length,1,'isolated recorded zero stays visible')
 await click('Go to recorded peak · 0.00 Hz / 1.00 s');assert.equal(seeks.at(-1),1)
})

test('local neuron selection opens its own history and peak seeks the surrounding replay',async()=>{
 const {BrainTheater}=require('./src/features/arena/MatchObservations.js')
 const seeks=[]
 const subject={...own,artifact_id:'compiled-design',brain_graph:{schema:'brain-neighborhood/v1',artifact_id:'compiled-design',connectome_sha256:spec.connectome_sha256,circuits:{olfactory:connectedGraph}}}
 const frames=[0,1,2].map((time,i)=>({time,brain:[{sampled_nodes:[{id:'a',activity:[0,20,0][i]},{id:'b',activity:[0,0,10][i]}]}]}))
 await mount(BrainTheater,{frame:frames[0],frames,fly:subject,slot:0,season:{connectome:{circuits:[]}},events:[],activityScale:20,nodeScale:20,onSeek:t=>seeks.push(t)})
 await click('Local graph')
 assert.equal(document.querySelector('.neuron-activity-trace').dataset.neuronId,'a')
 await click('Go to recorded peak · 20.00 Hz / 1.00 s');assert.equal(seeks.at(-1),1)
 await act(async()=>document.querySelector('[data-neuron="b"]').dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true})))
 assert.equal(document.querySelector('.neuron-activity-trace').dataset.neuronId,'b')
 await click('Go to recorded peak · 10.00 Hz / 2.00 s');assert.equal(seeks.at(-1),2)
 await act(async()=>{const el=document.querySelector('select[aria-label="Focus neuron"]');el.value='c';el.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(document.querySelector('.neuron-activity-trace').textContent,/did not record this neuron/)
})

test('recorded tactile group opens actual cell class, weights and history without coloring unsampled neighbors',async()=>{
 const {BrainTheater}=require('./src/features/arena/MatchObservations.js'),seeks=[]
 const tactile={neurons:[{id:'touch-r',class:'mechanosensory_tactile'},{id:'neighbor',class:'other'}],edges:[{pre:'touch-r',post:'neighbor',edge:2,count:4,baseline_weight:1.1,weight:1.32,multiplier:1.2}],anchors:['touch-r']}
 const empty={neurons:[],edges:[]}
 const display={id:'touch_right',label:'Right environmental touch',name:'Right touch',color:'#76a8df',neuron_count:1294,edge_count:20}
 const subject={...own,artifact_id:'sensory-design',brain_graph:{schema:'brain-neighborhood/v1',artifact_id:'sensory-design',connectome_sha256:spec.connectome_sha256,circuits:{olfactory:empty,touch_right:tactile},display_groups:[display]}}
 const frames=[0,1].map((time,i)=>({time,brain:[{circuits:{touch_right:i*9},sampled_nodes:[{id:'touch-r',activity:i*12}]}]}))
 const props={matchId:'sensory-match',frame:frames[1],frames,fly:subject,slot:0,season:{connectome:{circuits:[]}},events:[],activityScale:20,nodeScale:20,onSeek:t=>seeks.push(t)}
 await mount(BrainTheater,props)
 await click('Functional region')
 await click('Right environmental touch')
 const region=document.querySelector('[data-circuit="touch_right"]');assert.equal(region.dataset.recorded,'true')
 assert.ok(document.querySelector('.brain-overview-map').getAttribute('viewBox').endsWith('585'))
 await act(async()=>region.dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true})))
 assert.match(document.querySelector('.brain-class-list').textContent,/mechanosensory_tactile/)
 await act(async()=>document.querySelector('.brain-class-list button').click())
 assert.equal(document.querySelector('.neuron-activity-trace').dataset.neuronId,'touch-r')
 await click('Go to recorded peak · 12.00 Hz / 1.00 s');assert.equal(seeks.at(-1),1)
 await act(async()=>{const select=document.querySelector('select[aria-label="Focus neuron"]');select.value='neighbor';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(document.querySelector('.neuron-activity-trace').textContent,/did not record this neuron/)
 await click('Anatomical space · 3D')
 await click('Right environmental touch')
 assert.ok(document.querySelector('.local-brain-neighborhood'),'missing anatomical coordinates open the usable connection view')
 assert.match(document.querySelector('.brain-missing-coordinates').textContent,/coordinates are unavailable/)
 assert.equal(document.querySelector('.neuron-activity-trace').dataset.neuronId,'touch-r')
 assert.match(document.querySelector('.local-brain-edge-details').textContent,/1\.3200/)
 await mount(BrainTheater,{...props,frame:frames[0]})
 assert.equal(document.querySelector('.neuron-activity-trace').dataset.neuronId,'touch-r')
 assert.match(document.querySelector('.local-brain-node-details').textContent,/0\.00 Hz/)
 await mount(BrainTheater,{...props,matchId:'historical-match',fly:{...subject,brain_graph:{...subject.brain_graph,circuits:{olfactory:empty},display_groups:undefined}}})
 assert.ok(![...document.querySelectorAll('.brain-circuit-tabs button')].some(b=>b.textContent.includes('Right environmental touch')))
})

const {anatomySpace,spatialNodes,validateAnatomy}=require('./src/features/arena/anatomy.js')
const {AnatomicalBrain}=require('./src/features/arena/AnatomicalBrain.js')
const anatomyFixture=sha=>({schema:'connectome-anatomy/v1',connectome_sha256:sha,neuron_count:3,position_count:2,missing_position_count:1,positions:[0,0,0,10,20,30]})
const positionedGraph={neurons:[{id:'a',class:'input',position:[0,0,0]},{id:'b',class:'projection',position:[10,20,30]},{id:'c',class:'other',position:null}],edges:connectedGraph.edges}
test('anatomy keeps uniform source geometry and missing positions distinct from silence',()=>{
 const data=validateAnatomy(anatomyFixture('a'.repeat(64)),'a'.repeat(64)),space=anatomySpace(data)
 assert.deepEqual(space.center,[5,10,15]);assert.equal(space.extent,15)
 const nodes=spatialNodes(positionedGraph,space,new Map([['a',0],['b',8],['c',4]]))
 assert.deepEqual(nodes[0],{id:'a',position:[-1/3,-2/3,-1],activity:0})
 assert.equal(nodes[2].position,null);assert.equal(nodes[2].activity,4)
 assert.equal(spatialNodes(positionedGraph,space,new Map())[0].activity,null)
 assert.throws(()=>validateAnatomy(data,'b'.repeat(64)))
 assert.throws(()=>validateAnatomy({...data,position_count:3},data.connectome_sha256))
 assert.throws(()=>validateAnatomy({...data,positions:[NaN,0,0,10,20,30]},data.connectome_sha256))
 assert.deepEqual([...anatomySpace({...data,positions:[],position_count:0}).positions],[])
})
test('anatomical brain uses matching static coordinates, selects real neurons and retains missing-position traces',async()=>{
 const sha='c'.repeat(64),requests=[],seeks=[]
 globalThis.fetch=async url=>{requests.push(String(url));return String(url).startsWith('/api/')?{ok:false}:{ok:true,json:async()=>anatomyFixture(sha)}}
 const frames=[0,1].map((time,i)=>({time,brain:[{sampled_nodes:[{id:'a',activity:i*12},{id:'b',activity:i*5},{id:'c',activity:i*7}]}]}))
 const props={connectome:sha,graph:positionedGraph,activity:new Map([['a',0],['b',0],['c',0]]),scale:12,frames,slot:0,time:0,onSeek:t=>seeks.push(t)}
 await mount(AnatomicalBrain,props)
 assert.deepEqual(requests.filter(url=>!url.endsWith('/morphology')),['/api/v1/connectome/anatomy','/examples/anatomy/'+sha+'.json'])
 assert.match(document.querySelector('.anatomical-brain-counts').textContent,/2 actual soma positions.*1 neurons without coordinates/)
 assert.equal(spatialCanvasProps.space.positions.length,6)
 assert.equal(document.querySelector('[aria-label="Spatial neuron a"]').dataset.activity,'0')
 await click('Spatial neuron b');assert.equal(document.querySelector('select[aria-label="Focus neuron"]').value,'b')
 await click('Go to recorded peak · 5.00 Hz / 1.00 s');assert.equal(seeks.at(-1),1)
 await click('XZ');assert.equal(spatialCanvasProps.angle,'xz')
 await mount(AnatomicalBrain,{...props,time:1,activity:new Map([['a',12],['b',5],['c',7]])})
 assert.equal(spatialCanvasProps.focus,'b');assert.equal(spatialCanvasProps.scale,12)
 assert.equal(document.querySelector('[aria-label="Spatial neuron b"]').dataset.activity,'5')
 await act(async()=>{const select=document.querySelector('select[aria-label="Focus neuron"]');select.value='c';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.equal(spatialCanvasProps.focus,'c');assert.equal(document.querySelector('[aria-label="Spatial neuron c"]'),null)
 assert.match(document.querySelector('.anatomical-brain-position').textContent,/Unavailable/)
 await click('Go to recorded peak · 7.00 Hz / 1.00 s');assert.equal(seeks.at(-1),1)
 // Same anatomy can be reused across participants, but activity must change.
 await mount(AnatomicalBrain,{...props,activity:new Map(),slot:1})
 assert.equal(document.querySelector('[aria-label="Spatial neuron b"]').dataset.activity,'missing')
 assert.equal(requests.filter(url=>!url.endsWith('/morphology')).length,2)
})
test('anatomical view rejects another connectome and discards a late response after switching replay',async()=>{
 let resolveOld
 const old='d'.repeat(64),next='e'.repeat(64)
 globalThis.fetch=async url=>String(url).endsWith('/morphology')?{ok:false}:String(url).startsWith('/api/')?new Promise(resolve=>{resolveOld=resolve}):{ok:true,json:async()=>anatomyFixture(old)}
 const props={connectome:old,graph:positionedGraph,activity:new Map(),scale:1,frames:[],slot:0,time:0,onSeek:noop}
 await mount(AnatomicalBrain,props)
 globalThis.fetch=async()=>({ok:true,json:async()=>anatomyFixture('f'.repeat(64))})
 await mount(AnatomicalBrain,{...props,connectome:next})
 assert.match(document.body.textContent,/Matching anatomical coordinates are unavailable/)
 assert.equal(document.querySelector('[data-spatial-canvas]'),null)
 await act(async()=>resolveOld({ok:true,json:async()=>anatomyFixture(old)}))
 assert.equal(document.querySelector('[data-spatial-canvas]'),null)
 assert.ok(document.querySelector('.local-brain-canvas'),'structural inspection remains usable')
})

test('anatomical replay starts with all recorded circuits and can focus and restore a circuit',async()=>{
 const {BrainTheater}=require('./src/features/arena/MatchObservations.js')
 const sha='9'.repeat(64),descending={neurons:[{id:'d',class:'descending',position:[5,10,15]}],edges:[]}
 globalThis.fetch=async()=>({ok:true,json:async()=>anatomyFixture(sha)})
 const fly={...own,spec:{...spec,connectome_sha256:sha},artifact_id:'own-artifact',brain_graph:{schema:'brain-neighborhood/v1',artifact_id:'own-artifact',connectome_sha256:sha,circuits:{olfactory:positionedGraph,descending}}}
 const frame={time:1,brain:[{sampled_nodes:[{id:'a',activity:1},{id:'d',activity:15}]}]}
 await mount(BrainTheater,{fly,frame,frames:[frame],season:{connectome:{circuits:[{id:'olfactory',label:'Olfactory receptors'},{id:'descending',label:'Descending neurons'}]}},slot:0,events:[],activityScale:20,nodeScale:20,onSeek:noop})
 assert.ok(document.querySelector('.anatomical-brain-stage'),'a bound anatomical replay opens directly in spatial view')
 await click('Anatomical space · 3D')
 assert.deepEqual(spatialCanvasProps.nodes.map(n=>n.id),['a','b','c','d'])
 await click('Spatial neuron d')
 assert.equal(document.querySelector('.neuron-activity-trace').dataset.neuronId,'d')
 await click('Descending neurons');assert.deepEqual(spatialCanvasProps.nodes.map(n=>n.id),['d'])
 await click('All recorded circuits');assert.deepEqual(spatialCanvasProps.nodes.map(n=>n.id),['a','b','c','d'])
})


test('training workload counts both brains separately from swapped matches and reacts to language',async()=>{
 const {TrainingWorkload}=require('./src/features/training/TrainingWorkload.js')
 const props={population:2,generations:2,duration:10,mode:'contest',conditions:[{map_id:'orchard',seed:42},{map_id:'orchard',seed:43}]}
 await mount(TrainingWorkload,props)
 const text=()=>document.querySelector('.training-workload').textContent
 assert.match(text(),/Per evaluation10 s · 2 flies/)
 assert.match(text(),/Planned simulation time160 s/)
 assert.match(text(),/Simulation time across all brains320 s/)
 assert.match(text(),/not a completion countdown/)
 await mount(TrainingWorkload,{...props,mode:'forage',duration:1})
 assert.match(text(),/Planned simulation time8 s/)
 assert.match(text(),/Simulation time across all brains8 s/)
 assert.match(text(),/may not have time to reach food/)
 const language=document.querySelector('select[aria-label="Language"]')
 await act(async()=>{language.value='zh-CN';language.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.match(text(),/计划总仿真时长8 s/)
 await mount(TrainingWorkload,{...props,population:NaN})
 assert.doesNotMatch(text(),/NaN|Infinity/)
})

test('zero intake, inversion, equal contest advantage and missing behavior stay distinct beside replay',async()=>{
 const {ConditionResults}=require('./src/features/training/ConditionResults.js')
 const metric={schema:'sustained-foraging-v1',food:0,latter_half_food:0,upright_fraction:.327,recorded_seconds:10,first_inversion_s:3.27,fitness:0}
 const match={id:'recorded-match',status:'verified',request:{mode:'contest'},result:{behavior:[metric,{...metric,food:10,latter_half_food:2,fitness:12,upright_fraction:1,first_inversion_s:null}]}}
 const result={condition:{map_id:'enclosure',seed:43},fitness:0,evaluations_completed:2,evaluations_total:2,matches:[match]}
 const replay=[]
 await mount(ConditionResults,{results:[result],maps:[],onReplay:m=>replay.push(m.id)})
 assert.match(document.body.textContent,/no average advantage/)
 assert.match(document.body.textContent,/Recorded 10.00 s · No intake recorded in this window. First inversion 3.27 s/)
 assert.match(document.body.textContent,/Total food 10.000. No inversion recorded/)
 await click('Behavior and neural replay 1 · Replay');assert.deepEqual(replay,['recorded-match'])
 await mount(ConditionResults,{results:[{...result,fitness:null,matches:[{...match,request:{mode:'forage'},result:{behavior:[null]}}]}],maps:[],onReplay:noop})
 assert.match(document.body.textContent,/Awaiting complete condition/)
 assert.doesNotMatch(document.body.textContent,/No intake|First inversion|no average advantage/)
})

test('event response pairs the same neurons and contestant without turning missing samples into zero',async()=>{
 const {EventNeuralResponse,pairedNeuralChanges}=require('./src/features/arena/EventNeuralResponse.js')
 const sample=(nodes)=>({sampled_nodes:nodes.map(([id,activity])=>({id,activity}))})
 const before={time:1,brain:[sample([['a',0],['b',30],['lost',50],['invalid',NaN]]),sample([['a',999]])]}
 const after={time:1.1,brain:[sample([['a',10],['b',5],['new',100],['invalid',4]]),sample([['a',0]])]}
 const response=pairedNeuralChanges(before,after,0)
 assert.equal(response.paired,2);assert.equal(response.unpaired,3)
 assert.deepEqual(response.changes.map(n=>[n.id,n.delta]),[['b',-25],['a',10]])
 const seeks=[],nodes=[]
 await mount(EventNeuralResponse,{before,after,slot:0,time:1,graph:connectedGraph,onSeek:t=>seeks.push(t),onInspect:id=>nodes.push(id)})
 assert.match(document.body.textContent,/2 neurons recorded at both samples; 3 at only one/)
 await click('Inspect responding neuron b');assert.deepEqual(seeks,[1.1]);assert.deepEqual(nodes,['b'])
 await click('View before / at event · 1.00 s');assert.equal(seeks.at(-1),1)
 await mount(EventNeuralResponse,{before,after:before,slot:0,time:1,graph:connectedGraph,onSeek:noop,onInspect:noop})
 assert.match(document.body.textContent,/no two distinct samples/);assert.equal(document.querySelector('[data-response-neuron]'),null)
})

test('an event opens the responding neuron with its actual weights and retains focus when seeking before and after',async()=>{
 const {BrainTheater}=require('./src/features/arena/MatchObservations.js')
 const graph={neurons:connectedGraph.neurons.filter(n=>n.id!=='b'),edges:[]}
 const fly={...own,artifact_id:'event-brain',brain_graph:{schema:'brain-neighborhood/v1',artifact_id:'event-brain',connectome_sha256:spec.connectome_sha256,circuits:{olfactory:graph,projection:connectedGraph}}}
 const frame=(time,a,b)=>({time,tick:Math.round(time*10000),brain:[{circuits:{olfactory:a,projection:b},sampled_nodes:[{id:'a',activity:a},{id:'b',activity:b}]}]})
 const frames=[frame(1,0,30),frame(1.01,1,28),frame(1.1,10,5)]
 const seeks=[];const props={frames,events:[{type:'food_contact',tick:10000,slot:0}],season:{connectome:{circuits:[{id:'olfactory',label:'Olfactory',color:'#090'},{id:'projection',label:'Projection',color:'#909'}]}},fly,slot:0,activityScale:30,nodeScale:30,onSeek:t=>seeks.push(t)}
 globalThis.fetch=()=>{throw Error('Frozen graph must not need a network lookup')}
 await mount(BrainTheater,{...props,frame:frames[0]})
 await click('1.00sFood contact');assert.equal(seeks.at(-1),1.1)
 await mount(BrainTheater,{...props,frame:frames[2]})
 await click('Inspect responding neuron b')
 assert.equal(document.querySelector('select[aria-label="Focus neuron"]').value,'b')
 assert.equal(document.querySelector('.neuron-activity-trace').dataset.neuronId,'b')
 assert.match(document.querySelector('.local-brain-node-details').textContent,/5.00 Hz/)
 assert.match(document.querySelector('.local-brain-edge-details').textContent,/6.6000/)
 await click('View before / at event · 1.00 s');assert.equal(seeks.at(-1),1)
 await mount(BrainTheater,{...props,frame:frames[0]})
 assert.equal(document.querySelector('select[aria-label="Focus neuron"]').value,'b')
 assert.match(document.querySelector('.local-brain-node-details').textContent,/30.00 Hz/)
 await click('View response sample · 1.10 s');assert.equal(seeks.at(-1),1.1)
})

test('research offspring retains kernel senses in playable unranked match setup',async()=>{
 const canvasFile=require.resolve('./src/ArenaCanvas.js')
 require.cache[canvasFile]={id:canvasFile,filename:canvasFile,loaded:true,exports:{ArenaCanvas:()=>null}}
 delete require.cache[require.resolve('./src/features/arena/ArenaFeature.js')]
 const {ArenaFeature}=require('./src/features/arena/ArenaFeature.js')
 const {compatibleSensory,defaultMatchProfile}=require('./src/types.js')
 const kernel='sensorimotor-research-v2',senses='engineered-kernel-contact-v1';let submitted=0
 const season={connectome:{circuits:[]},match_profiles:[{id:kernel,name:'Research',ready:false,sandbox_ready:true,sensory_profiles:['odor-only-v1',senses]}],sensory_profiles:[{id:senses,name:'Kernel contact',ready:true},{id:'legacy-touch',ready:true}]}
 assert.equal(defaultMatchProfile(season),kernel)
 assert.equal(compatibleSensory(season,kernel,senses),true)
 assert.equal(compatibleSensory(season,kernel,'legacy-touch'),false)
 const props={scene:null,frame:null,next:null,alpha:0,focused:'',preview:null,selectedFly:own,chosenMap:null,current:null,selected:own.id,identity:null,flies:[own,wt],frames:[],events:[],play:false,playtime:0,playbackSpeed:1,season,matches:[],maps:[],mapId:'enclosure',mode:'contest',opponent:wt.id,duration:20,seed:42,busy:'',bridgeProfile:kernel,sensoryProfile:senses,replayStatus:'idle',replayError:'',startMatch:()=>submitted++}
 for(const key of ['setSelected','setSensoryProfile','setBridgeProfile','setPlay','setPlaytime','setPlaybackSpeed','setFocused','setMapId','setMode','setOpponent','setDuration','setSeed','startSeries'])props[key]=noop
 await mount(ArenaFeature,props)
 const select=document.querySelector('select[aria-label="Sensory input profile"]')
 assert.equal(select.disabled,false);assert.equal(select.value,senses)
 assert.deepEqual([...select.options].map(o=>o.value),['odor-only-v1',senses])
 assert.match(document.body.textContent,/Results stay outside the public leaderboard/)
 await click('Start match');assert.equal(submitted,1)
})

const {morphologyActivity,validateMorphology}=require('./src/features/arena/morphology.js')
test('real fiber activity distinguishes zero from missing and changes with the observed contestant',()=>{
 const neurons=['10','20','30'].map(id=>({id,positions:[0,0,0,8,8,8],edges:[0,1],radii:[1,1]}))
 const value={schema:'connectome-morphology/v1',connectome_sha256:'a'.repeat(64),coordinate_unit_nm:8,neurons}
 assert.equal(validateMorphology(value,'a'.repeat(64)),value)
 assert.throws(()=>validateMorphology(value,'b'.repeat(64)))
 assert.throws(()=>validateMorphology({...value,neurons:[{...neurons[0],edges:[0,2]}]},'a'.repeat(64)))
 const first=morphologyActivity(neurons,new Map([['10',0],['20',100]]),100,null)
 assert.equal(first[0],0);assert.equal(first[1],255,'zero has a recorded flag')
 assert.equal(first[4],255);assert.equal(first[5],255)
 assert.equal(first[8],0);assert.equal(first[9],0,'missing remains unrecorded')
 const other=morphologyActivity(neurons,new Map([['30',50]]),100,'10')
 assert.equal(other[1],0);assert.equal(other[2],255,'selection is separate from activity')
 assert.ok(other[8]>0);assert.equal(other[9],255)
})
