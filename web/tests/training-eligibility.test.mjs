import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {JSDOM} from 'jsdom'
import * as icons from 'lucide-react'

function moduleUrl(url){
 const {outputText}=ts.transpileModule(fs.readFileSync(url,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}})
 return 'data:text/javascript;base64,'+Buffer.from(outputText.replace(/from (['"])(\.[^'"]+)\1/g,(_,quote,path)=>`from ${quote}${moduleUrl(new URL(path+'.ts',url))}${quote}`)).toString('base64')
}
const moduleAt=path=>import(moduleUrl(new URL(path,import.meta.url)))
const eligibility=await moduleAt('../src/features/training/trainingEligibility.ts')
const {mapEligibility}=await moduleAt('../src/types.ts')
const {trainingMapIds,trainingBridgeProfiles,trainingEligibilityProblem,eligibleTrainingMaps}=eligibility
const plan=await moduleAt('../src/features/training/plan.ts')
const {trainingMessages}=await moduleAt('../src/shared/messages/training.ts')
const base={population:2,generations:1,budget:16,duration:1,seed:42,circuits:['olfactory'],name:'Contract test',mode:'forage',founder:'a'.repeat(32),opponent:'b'.repeat(32)}
const maps=[...trainingMapIds,'maze','switchback','labyrinth','duel','unknown'].map(id=>({id,name:id,english:id,description:'',task:id==='blank'?{}:undefined}))

test('frontend map and bridge lists exactly equal both backend training declarations',()=>{
 const source=fs.readFileSync(new URL('../../src/flyarena/services/training.py',import.meta.url),'utf8')
 function field(className,name){
  const body=source.split(`class ${className}(StrictModel):`)[1]?.split(/\nclass /)[0]
  const literal=body?.match(new RegExp(`${name}: Literal\\[([^\\]]+)\\]`))?.[1]
  assert.ok(literal,`Missing ${className}.${name} contract`)
  return [...literal.matchAll(/['"]([^'"]+)['"]/g)].map(m=>m[1])
 }
 assert.deepEqual(trainingMapIds,field('TrainingSpec','map_id').filter(id=>mapEligibility({id}).training_eligible))
 assert.deepEqual(trainingMapIds,field('EvaluationCondition','map_id').filter(id=>mapEligibility({id}).training_eligible))
 assert.deepEqual(trainingBridgeProfiles,field('TrainingSpec','bridge_profile'))
})

test('selectors and plan validation agree for every map, bridge and training mode',()=>{
 for(const bridge_profile of [...trainingBridgeProfiles,'unknown'])for(const mode of ['forage','contest']){
  const selected=eligibleTrainingMaps(maps,bridge_profile,mode).map(m=>m.id)
  for(const {id:map_id} of maps){
   const expected=trainingBridgeProfiles.includes(bridge_profile)&&trainingMapIds.includes(map_id)&&!(map_id==='blank'&&mode==='contest')
   assert.equal(selected.includes(map_id),expected,`${map_id}/${bridge_profile}/${mode}`)
   assert.equal(trainingEligibilityProblem(map_id,bridge_profile,mode)===null,expected)
   assert.equal(plan.planProblem({...base,map_id,bridge_profile,mode})===null,expected)
   assert.equal(plan.planProblem({...base,bridge_profile,mode,conditions:[{map_id:'orchard',seed:42},{map_id,seed:43}]})===null,expected)
  }
 }
})

test('eligibility errors have actionable English and Chinese messages',()=>{
 for(const args of [['unknown','legacy-v1','forage'],['orchard','unknown','forage'],['blank','legacy-v1','contest']]){
  const key=trainingEligibilityProblem(...args)
  for(const locale of ['en','zh-CN'])assert.ok(trainingMessages[key]?.[locale]?.trim(),`${key}/${locale}`)
 }
})

// Exercise real training selectors with a stubbed geometry preview, not a simulated run.
for(const locale of ['en','zh-CN'])test(`training controls preserve eligibility and preview the chosen bridge (${locale})`,async()=>{
 const dom=new JSDOM('<main id="root"></main>',{url:'http://arena.example/'})
 const keys=['window','document','location','history','requestAnimationFrame','IS_REACT_ACT_ENVIRONMENT']
 const originals=Object.fromEntries(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const k of keys)Object.defineProperty(globalThis,k,{configurable:true,writable:true,value:k==='IS_REACT_ACT_ENVIRONMENT'?true:k==='requestAnimationFrame'?()=>1:dom.window[k]})
 const t=key=>trainingMessages[key]?.[locale]||key
 const noop=()=>null
 const dependencies={
  'react':React,'react/jsx-runtime':await import('react/jsx-runtime'),'lucide-react':icons,
  './trainingEligibility':eligibility,'./plan':plan,
  '../life/navigation':{lifeHash:()=>'',continuationFocus:()=>''},'../../api':{api:()=>{throw Error('Unexpected training request')},newRequestKey:()=>''},
  '../../shared/i18n':{useI18n:()=>({t,locale})},
  '../arena/MapPreview':{MapPreview:props=>React.createElement('div',{'data-preview-map':props.mapId,'data-preview-bridge':props.bridgeProfile})},
  '../guide/nextAction':{useGuideEvidence:()=>({record:null,error:''})},
  './FirstExperimentGuide':{FirstExperimentGuide:noop},'./AlgorithmPicker':{AlgorithmPicker:noop},'./TrainingShowcase':{TrainingShowcase:noop},'./algorithms':{algorithmName:id=>id},
  './TrainingComparison':{TrainingComparison:noop},'./TrainingWorkload':{TrainingWorkload:noop},'./ConditionResults':{ConditionResults:noop},'./comparison':{evaluationConditions:spec=>spec.evaluation_conditions||[{map_id:spec.map_id,seed:spec.seed}]}
 }
 const source=fs.readFileSync(new URL('../src/features/training/TrainingSandbox.tsx',import.meta.url),'utf8')
 const {outputText}=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}})
 const compiled={exports:{}}
 new Function('require','module','exports',outputText)(id=>{assert.ok(id in dependencies,`Unstubbed dependency: ${id}`);return dependencies[id]},compiled,compiled.exports)
 const root=createRoot(document.getElementById('root'))
 try{
  const fly={id:base.founder,name:'Fixture fly',spec:{model_profile:'malecns-lif-cpu-v1'}}
  await act(async()=>root.render(React.createElement(compiled.exports.TrainingSandbox,{flies:[fly,{...fly,id:base.opponent}],identity:null,selected:fly.id,maps,season:{connectome:{circuits:[]},training_bridge_profiles:trainingBridgeProfiles.map(id=>({id,ready:true}))},onLogin:noop,onSaved:noop,onCompete:noop,onReplay:noop})))
  const select=label=>[...document.querySelectorAll('label')].find(el=>el.firstChild?.textContent===label)?.querySelector('select')
  const button=label=>[...document.querySelectorAll('button')].find(el=>el.textContent.trim()===label)
  const change=async(el,value)=>{assert.ok(el);await act(async()=>{el.value=value;el.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})}
  const environment=select('Environment')
  assert.deepEqual([...environment.options].map(o=>o.value),trainingMapIds)
  await change(environment,'canopy')
  await change(document.getElementById('training-bridge-profile'),'sensorimotor-research-v2')
  assert.equal(document.querySelector('[data-preview-map]').dataset.previewMap,'canopy')
  assert.equal(document.querySelector('[data-preview-bridge]').dataset.previewBridge,'sensorimotor-research-v2')
  assert.equal(button('Start training').disabled,false)
  await act(async()=>button('Add evaluation condition').click())
  const extra=document.querySelector('.extra-condition select')
  assert.deepEqual([...extra.options].map(o=>o.value),trainingMapIds)
  await change(extra,'canopy')
  await change(extra,'blank')
  await change(select('Objective'),'contest')
  assert.equal(extra.value,'blank')
  assert.equal(extra.selectedOptions[0].disabled,true)
  assert.ok(document.body.textContent.includes(t(trainingEligibilityProblem('blank','sensorimotor-research-v2','contest'))))
  await change(extra,'canopy')
  await change(select('Objective'),'forage')
  await change(environment,'blank')
  await change(select('Objective'),'contest')
  assert.equal(environment.value,'blank')
  assert.equal(environment.selectedOptions[0].disabled,true)
  assert.ok(![...extra.options].some(o=>o.value==='blank'))
  assert.equal(document.querySelector('[data-preview-map]'),null)
  assert.ok(document.body.textContent.includes(t(trainingEligibilityProblem('blank','sensorimotor-research-v2','contest'))))
  assert.equal(button('Start training').disabled,true)
  await change(environment,'canopy')
  assert.equal(document.querySelector('[data-preview-bridge]').dataset.previewBridge,'sensorimotor-research-v2')
  await act(async()=>button('Remove condition 2').click())
  await change(select('Objective'),'forage')
  assert.equal(button('Start training').disabled,false)
 }finally{
  await act(async()=>root.unmount());dom.window.close()
  for(const [key,descriptor]of Object.entries(originals)){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key]}
 }
})

test('catalog flags can further restrict both training selectors and admission',()=>{
 const metadata={training_eligible:false}
 assert.deepEqual(eligibleTrainingMaps([{id:'orchard',metadata}]),[])
 assert.ok(trainingEligibilityProblem('orchard','legacy-v1','forage',metadata))
})
