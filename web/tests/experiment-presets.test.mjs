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
const out=fs.mkdtempSync(path.join(os.tmpdir(),'experiment-presets-'))
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

const {experimentPresets,applyExperimentPreset,presetAvailable}=require('./src/features/arena/experimentPresets.js')
const {buildExperimentPlan}=require('./src/features/arena/experimentSetup.js')
const {ExperimentSetup}=require('./src/features/arena/ExperimentSetupPanel.js')
const {mapsMessages}=require('./src/shared/messages/maps.js')
const spec={connectome_sha256:'c'.repeat(64),model_profile:'malecns-lif-cpu-v1'}
const subject={id:'a'.repeat(32),spec},wt={id:'b'.repeat(32),spec,reference_kind:'wildtype'},spoof={id:'c'.repeat(32),name:'WT',spec,reference_kind:'user'}
const setup={selected:subject.id,opponent:spoof.id,mapId:'orchard',mode:'forage',seedText:'9',duration:2,bridgeProfile:'legacy-v1',sensoryProfile:'odor-only-v1'}
const maps=[{id:'scarcity',modes:['forage','contest']},{id:'duel',modes:['duel']},{id:'labyrinth',modes:['forage']}]
const season={match_profiles:[{id:'legacy-v1',ready:true}]}
test('questions create editable plans with exact map, schedule and existing submission paths',()=>{
 const snapshot=JSON.stringify(setup),plans=experimentPresets.map(p=>{
  assert.ok(presetAvailable(p,maps))
  const next=applyExperimentPreset(p,setup,[subject,wt,spoof])
  assert.equal(next.selected,subject.id);assert.equal(next.bridgeProfile,setup.bridgeProfile);assert.equal(next.sensoryProfile,setup.sensoryProfile)
  return buildExperimentPlan(next,[subject,wt,spoof],maps,season).plan
 })
 assert.equal(JSON.stringify(setup),snapshot)
 assert.deepEqual(plans.map(p=>p.submissions[0].endpoint),['/tournaments','/observation-series','/observation-series'])
 assert.deepEqual(plans.map(p=>p.matches.length),[4,4,3])
 assert.equal(plans[0].setup.opponent,wt.id);assert.equal(plans[1].setup.opponent,spoof.id);assert.equal(plans[2].setup.opponent,'')
 assert.ok(plans[2].matches.every(m=>m.fly_ids.length===1&&m.map_id==='labyrinth'))
 const edited=buildExperimentPlan({...plans[2].setup,duration:60,seedText:'7'},[subject],maps,season).plan
 assert.equal(edited.matches.length,1);assert.equal(edited.matches[0].seed,7);assert.equal(edited.matches[0].duration_seconds,60)
})
test('WT preset requires server provenance and compatible graph/model; missing WT stays explicit',()=>{
 const preset=experimentPresets[0]
 for(const flies of [[subject,spoof],[subject,{...wt,spec:{...spec,connectome_sha256:'other'}}],[subject,{...wt,spec:{...spec,model_profile:'other'}}]]){
  const next=applyExperimentPreset(preset,setup,flies)
  assert.equal(next.opponent,'');assert.equal(buildExperimentPlan(next,flies,maps,season).plan,null)
 }
 assert.equal(presetAvailable(preset,[]),false)
 assert.equal(presetAvailable(preset,[{...maps[0],metadata:{competition_eligible:false}}]),false)
})
test('every question states its evidence and limitations in both languages',()=>{
 for(const preset of experimentPresets)for(const suffix of ['question','scope']){
  const message=mapsMessages['presets.'+preset.id+'.'+suffix];assert.ok(message.en);assert.ok(message['zh-CN'])
 }
 assert.match(mapsMessages['presets.maze.scope'].en,/#82.*not validated navigation.*passes through walls.*not the preregistered/)
 assert.match(mapsMessages['presets.center.scope'].en,/No natural aggression/)
 assert.match(mapsMessages['presets.scarcity.scope'].en,/not general superiority/)
})

for(const locale of ['en','zh-CN'])test(`question cards have explicit native buttons, selected state and editable plans in ${locale}`,async()=>withDOM('',async(dom,mount)=>{
 localStorage.setItem('flyarena.locale',locale)
 const noop=()=>{},previews=[]
 let current
 globalThis.fetch=()=>{throw Error('Choosing a question must not submit work')}
 function Setup(){
  const [values,setValues]=React.useState(setup);current=values
  const setters=Object.fromEntries(Object.keys(setup).map(key=>['set'+key[0].toUpperCase()+key.slice(1),value=>setValues(old=>({...old,[key]:value}))]))
  return React.createElement(ExperimentSetup,{...values,...setters,flies:[subject,wt,spoof],identity:null,season,maps,busy:'',startMatch:()=>assert.fail('No computation'),onPreview:()=>previews.push(true),onDesign:noop})
 }
 await mount(Setup,{})
 const cards=[...document.querySelectorAll('.experiment-preset')]
 assert.equal(cards.length,3)
 for(const [index,card] of cards.entries()){
  const button=card.querySelector('button')
  assert.equal(button.type,'button');assert.equal(button.tabIndex,0)
  assert.equal(button.textContent,mapsMessages['presets.use'][locale])
  assert.ok(card.querySelector('h4').textContent.includes(mapsMessages['presets.'+experimentPresets[index].id+'.question'][locale]))
  button.focus();assert.equal(document.activeElement,button)
  // Native buttons supply Enter/Space activation in the browser; jsdom exercises the resulting click.
  await act(async()=>button.click())
  assert.equal(button.getAttribute('aria-pressed'),'true')
  assert.equal(card.classList.contains('selected'),true)
  assert.equal(document.querySelectorAll('.experiment-preset.selected').length,1)
  assert.ok(button.textContent.includes(mapsMessages['presets.selected'][locale]))
  assert.equal(current.mapId,experimentPresets[index].mapId)
 }
 // Changing a preset condition through its native select clears the selected card.
 const duration=[...document.querySelectorAll('select')].find(select=>[...select.options].some(option=>option.value==='300'))
 await act(async()=>{duration.value='60';duration.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 assert.equal(document.querySelectorAll('.experiment-preset.selected').length,0)
 assert.equal(previews.length,3)
}))
