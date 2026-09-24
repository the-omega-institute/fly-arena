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
const out=fs.mkdtempSync(path.join(os.tmpdir(),'guide-next-action-'))
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
const {nextGuideStep}=require('./src/features/guide/content.js')
const {guideSubject,guideComparisonPlan,baselineComparison,hasRecordedEvolution,useGuideEvidence}=require('./src/features/guide/nextAction.js')
const {PlaygroundGuide}=require('./src/features/guide/PlaygroundGuide.js')
const {guideMessages}=require('./src/shared/messages/guide.js')

test('next action advances only with saved designs and recorded comparison/evolution evidence',()=>{
 for(const [state,id] of [[{},'clone'],[{hasCompared:true,hasEvolved:true},'clone'],[{hasSavedDesign:true},'compare'],[{hasSavedDesign:true,hasCompared:true},'evolve'],[{hasSavedDesign:true,hasEvolved:true},'compete']])assert.equal(nextGuideStep(state).id,id)
 assert.equal(guideSubject([wt,fly],wt.id,'me'),fly)
 assert.equal(guideSubject([wt,fly],fly.id,'other'),undefined)
 assert.equal(guideSubject([wt,fly],fly.id),undefined)
 const own2={...fly,id:'other-own'};assert.equal(guideSubject([fly,own2],own2.id,'me'),own2)
})
test('WT preparation uses a compatible server reference and the exact Arena paired plan',()=>{
 const plan=guideComparisonPlan([fly,wt],fly.id,maps,season)
 assert.deepEqual(plan.setup,{selected:fly.id,opponent:wt.id,mapId:'orchard',mode:'contest',seedText:'42',duration:2,bridgeProfile:'legacy-v1',sensoryProfile:'odor-only-v1'})
 assert.equal(plan.submissions[0].endpoint,'/tournaments')
 assert.deepEqual(plan.matches.map(m=>m.fly_ids),[[fly.id,wt.id],[wt.id,fly.id]])
 assert.ok(plan.matches.every(m=>m.seed===42&&m.duration_seconds===2))
 for(const flies of [[fly],[fly,{...wt,reference_kind:'user',name:'WT'}],[fly,{...wt,spec:{...spec,model_profile:'other'}}],[fly,{...wt,spec:{...spec,connectome_sha256:'other'}}]])assert.equal(guideComparisonPlan(flies,fly.id,maps,season),null)
 assert.equal(guideComparisonPlan([fly,wt],wt.id,maps,season),null)
 assert.equal(guideComparisonPlan([fly,wt],fly.id,maps,null),null)
 assert.equal(guideComparisonPlan([fly,wt],fly.id,[],season),null)
 assert.equal(guideComparisonPlan([fly,wt],fly.id,[{id:'orchard'}],season),null)
 assert.equal(guideComparisonPlan([fly,wt],fly.id,maps,{...season,match_profiles:[{id:'legacy-v1',ready:false}]}),null)
})
test('failed, unpaired, missing-receipt and mismatched runs do not advance; verified zero effects do',()=>{
 const compare=matches=>baselineComparison([fly,wt],fly,matches)
 assert.deepEqual(compare([first,second]),[first,second])
 for(const patch of [{status:'failed'},{status:'running'},{result:null},{result:{receipt_sha256:''}},{request:{...second.request,seed:43}},{request:{...second.request,map_id:'ring'}},{request:{...second.request,duration_seconds:3}},{request:{...second.request,sensory_profile:'other'}},{request:{...second.request,bridge_profile:'other'}},{request:first.request}])assert.equal(compare([first,{...second,...patch}]),null)
 assert.equal(compare([first]),null);assert.equal(compare([]),null)
 assert.equal(baselineComparison([fly,{...wt,reference_kind:'user'}],fly,[first,second]),null)
})
test('a parent pointer or saved unscored training baseline is not completed evolution',()=>{
 const origin={strategy:'evolution',round:1,slot:1,fitness:0,saved:true}
 assert.equal(hasRecordedEvolution({fly,origin,experiences:[]},fly),true)
 for(const patch of [{fitness:null},{fitness:NaN},{saved:false},{strategy:'unknown'},{slot:0}])assert.equal(hasRecordedEvolution({fly,origin:{...origin,...patch},experiences:[]},fly),false)
 assert.equal(hasRecordedEvolution(null,fly),false)
 assert.equal(hasRecordedEvolution({fly:wt,origin,experiences:[]},fly),false)
})
for(const locale of ['en','zh-CN'])test(`next action leads, science is disclosed, collapse retains the action in ${locale}`,async()=>withDOM('',async(dom,mount)=>{
 localStorage.setItem('flyarena.locale',locale)
 globalThis.fetch=()=>{throw Error('Guide must not submit work')}
 const calls=[]
 const props={canCloneWT:true,canCompare:true,hasSavedDesign:false,onCloneWT:()=>calls.push('clone'),onCompare:()=>calls.push('compare'),onTrain:()=>calls.push('train'),onArena:()=>calls.push('compete'),onDesign:noop,onAI:noop}
 for(const [state,id] of [[{},'clone'],[{hasSavedDesign:true},'compare'],[{hasSavedDesign:true,hasCompared:true},'evolve'],[{hasSavedDesign:true,hasEvolved:true},'compete']]){
  await mount(PlaygroundGuide,{...props,...state})
  const next=document.querySelector('[data-guide-next]')
  assert.equal(next.dataset.guideNext,id)
  assert.ok(document.getElementById('playground-guide-title').textContent.includes(guideMessages[`guide.${id}.title`][locale]))
  for(const section of ['basis','value','meaning','data']){
   const details=document.querySelector(`[data-guide-section="${section}"] details`)
   assert.equal(details.open,false)
   assert.ok(details.textContent.includes(guideMessages[`guide.${section}.summary`][locale]))
  }
  await act(async()=>next.click())
 }
 assert.deepEqual(calls,['clone','compare','train','compete'])
 await act(async()=>document.querySelector('.playground-guide__collapse').click())
 assert.equal(document.querySelector('[data-guide-next]').dataset.guideNext,'compete')
 assert.equal(document.querySelector('[data-guide-section]'),null)
 await act(async()=>document.querySelector('.playground-guide__reopen').click())
 assert.ok(document.querySelector('[data-guide-section]'))
 assert.doesNotMatch(document.body.textContent,/guide\.[a-z]/)
}))
test('unavailable WT plan stays disabled and evidence fetch failures remain visible',async()=>withDOM('',async(dom,mount)=>{
 await mount(PlaygroundGuide,{canCloneWT:false,canCompare:false,hasSavedDesign:true,evidenceError:'Evidence offline',onCloneWT:noop,onCompare:()=>assert.fail('Cannot prepare'),onTrain:noop,onArena:noop,onDesign:noop,onAI:noop})
 assert.equal(document.querySelector('[data-guide-next]').disabled,true)
 assert.match(document.body.textContent,/Comparison is unavailable/)
 assert.match(document.body.textContent,/no completion is assumed.*Evidence offline/)
}))
test('life evidence follows the selected fly and stale responses cannot advance another fly',async()=>withDOM('',async(dom,mount)=>{
 const requests=[];let resolveFirst;let evidence
 globalThis.fetch=(url,options)=>{requests.push([String(url),options]);return new Promise(resolve=>{resolveFirst=resolve})}
 function Evidence({subject}){evidence=useGuideEvidence(subject,{id:'me'});return null}
 await mount(Evidence,{subject:fly})
 const resolveOld=resolveFirst
 await mount(Evidence,{subject:wt})
 assert.equal(requests[0][1].signal.aborted,true)
 await act(async()=>resolveOld({ok:true,json:async()=>({fly,origin:{saved:true}})}))
 assert.equal(evidence.record,null)
 await act(async()=>resolveFirst({ok:false,json:async()=>({detail:'Unavailable life record'})}))
 assert.match(evidence.error,/Unavailable life record/)
 assert.ok(requests.every(([,options])=>!options.method||options.method==='GET'))
}))
// Exercise App's handoff with real guide logic, replacing only unrelated workspaces/WebGL.
let arenaProps
for(const [module,names] of Object.entries({
 'ArenaCanvas':['ArenaCanvas'],
 'features/design/NeuralPreviewPanel':['NeuralPreviewPanel'],
 'features/design/BrainModelPicker':['BrainModelPicker'],
 'features/life/LifeLedger':['LifeLedger'],
 'features/training/TrainingSandbox':['TrainingSandbox'],
 'features/phenotype/PhenotypeLab':['PhenotypeLab'],
 'features/arena/ArenaFeature':['ArenaFeature'],
})){const file=require.resolve('./src/'+module+'.js');require.cache[file]={id:file,filename:file,loaded:true,exports:Object.fromEntries(names.map(name=>[name,props=>{if(name==='ArenaFeature')arenaProps=props;return null}]))}}
const App=require('./src/App.js').default
test('App comparison action installs the WT plan, selects the saved fly, and never submits work',async()=>withDOM('#tab=design',async(dom,mount)=>{
 const requests=[]
 localStorage.setItem('flyarena.identity',JSON.stringify({id:'me',name:'Designer',token:'fixture'}))
 globalThis.fetch=async(url,options={})=>{
  const endpoint=String(url).replace(/^.*\/api\/v1/,'');requests.push([endpoint,options.method||'GET'])
  const data=endpoint==='/auth/config'?{mode:'local'}:endpoint==='/me'?{id:'me',name:'Designer'}:endpoint==='/season'?{...season,default_bridge_profile:'sensorimotor-research-v2',connectome:{...season.connectome,neuron_count:1},budget:{points:100}}:endpoint==='/flies'?[wt,fly]:endpoint==='/maps'?maps:endpoint.startsWith('/lives/')?{fly,origin:null,experiences:[]}:endpoint==='/preview'?null:[]
  return {ok:true,json:async()=>data}
 }
 await mount(App,{})
 assert.equal(document.querySelector('[data-guide-next]').dataset.guideNext,'compare')
 await act(async()=>document.querySelector('[data-guide-next]').click())
 assert.equal(arenaProps.selected,fly.id);assert.equal(arenaProps.opponent,wt.id)
 assert.equal(arenaProps.mode,'contest');assert.equal(arenaProps.mapId,'orchard')
 assert.equal(arenaProps.duration,2);assert.equal(arenaProps.seedText,'42')
 assert.equal(arenaProps.bridgeProfile,'legacy-v1');assert.equal(arenaProps.sensoryProfile,'odor-only-v1')
 assert.equal(arenaProps.focused,'');assert.equal(arenaProps.seriesId,'')
 assert.equal(arenaProps.play,false);assert.match(location.hash,/tab=arena/)
 assert.ok(requests.every(([,method])=>method==='GET'))
}))
