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
const {ObservationSeries,ArenaObservations}=require('./src/features/arena/ObservationSeries.js')
const {I18nProvider}=require('./src/shared/i18n.js')
const {readRoute,routeHash}=require('./src/shared/navigation.js')
const {duelMessages}=require('./src/shared/messages/duel.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))
const flies=[{id:'a',name:'Design'},{id:'b',name:'Reference'}]
const fixture=(status='running')=>({id:'series-1',owner:'me',created:1,spec:{name:'Synthetic fixture',fly_ids:['a','b'],seeds:[42],map_id:'orchard',mode:'contest',duration_seconds:2},status,expected_matches:2,verified_matches:1,issues:[],unexpected_match_ids:[],standings:[],matches:[{id:'leg-1',status:'verified'},{id:'leg-2',status:'queued'}],schedule:[{seed:42,spawn_order:1,fly_ids:['a','b'],status:'verified',match_ids:['leg-1'],outcomes:[{fly_id:'a',score:2,outcome:'win'},{fly_id:'b',score:1,outcome:'loss'}],issues:[],errors:[]},{seed:42,spawn_order:2,fly_ids:['b','a'],status:'queued',match_ids:['leg-2'],outcomes:null,issues:[],errors:[]}]})
// DOM globals live inside each test and are restored only after React unmounts.
async function withDOM(run){
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://arena.example/#tab=arena&observation=series-1'})
 const keys=['window','document','navigator','localStorage','location','history','sessionStorage','matchMedia','IS_REACT_ACT_ENVIRONMENT','fetch','requestAnimationFrame','cancelAnimationFrame']
 const originals=Object.fromEntries(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const k of keys.slice(0,7))Object.defineProperty(globalThis,k,{configurable:true,writable:true,value:dom.window[k]})
 globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});globalThis.IS_REACT_ACT_ENVIRONMENT=true;globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{}
 const root=createRoot(document.getElementById('root'))
 const render=async(Component,props)=>act(async()=>root.render(React.createElement(I18nProvider,null,React.createElement(Component,props))))
 try{await run({root,render,dom})}finally{await act(async()=>root.unmount());dom.window.close();for(const [k,d]of Object.entries(originals)){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k]}}
}


const observationFixture=(status='running',solo=true)=>{
 const series=fixture(status);series.observation_only=solo;series.spec.mode=solo?'forage':'duel';series.spec.map_id=solo?'labyrinth':'duel'
 if(solo){series.spec.fly_ids=['a'];series.spec.seeds=[42,43];series.schedule=series.schedule.map((r,i)=>({...r,seed:42+i,spawn_order:1,fly_ids:['a'],outcomes:null}))}
 return series
}
test('observation deep link round trips with replay context and is independent of tournament IDs',()=>{
 const hash=routeHash('arena','','match & 1','','observation + 2'),route=readRoute(hash)
 assert.equal(route.observation,'observation + 2');assert.equal(route.match,'match & 1');assert.equal(route.series,'')
 assert.equal(readRoute('#observation=saved').tab,'arena')
})
test('solo report never turns completion or a supplied score into rankings',async()=>withDOM(async({render})=>{
 const series=observationFixture('complete');series.verified_matches=2;series.schedule[1].status='verified'
 // Even malformed scoring fields cannot render a solo score or conclusion.
 series.schedule[0].outcomes=[{fly_id:'a',score:9876,outcome:'win'}];series.standings=[{fly_id:'a',wins:2,points:6}]
 await render(ObservationSeries,{series,flies})
 assert.match(document.body.textContent,/Every scheduled observation is verified/)
 assert.match(document.body.textContent,/no scores, winner or standings/)
 assert.doesNotMatch(document.body.textContent,/9876|2 wins|6 points/)
 assert.equal(document.querySelectorAll('.series-conclusion').length,0)
 assert.match(document.querySelector('a[href*="match="]').getAttribute('href'),/match=leg-1&observation=series-1/)
}))
test('pending failed missing legs and measured errors remain visible without success claims',async()=>withDOM(async({render})=>{
 const series=observationFixture('incomplete');series.schedule[0].status='failed';series.schedule[0].errors=['Synthetic worker failure'];series.schedule[1].status='missing';series.schedule[1].match_ids=[]
 await render(ObservationSeries,{series,flies})
 assert.equal(document.querySelectorAll('tbody tr').length,2)
 assert.match(document.body.textContent,/Synthetic worker failure/);assert.match(document.body.textContent,/Missing/)
 assert.match(document.body.textContent,/observation plan is incomplete/);assert.doesNotMatch(document.body.textContent,/Every scheduled observation is verified/)
}))
test('duel series preserves leg outcomes but withholds aggregate until every swapped leg verifies',async()=>withDOM(async({render})=>{
 const series=observationFixture('running',false)
 await render(ObservationSeries,{series,flies})
 assert.match(document.body.textContent,/Win/);assert.match(document.body.textContent,/first-leg win remains a first-leg result/)
 assert.equal(document.querySelectorAll('.series-conclusion').length,0)
 series.status='complete';series.standings=[{fly_id:'a',wins:1,draws:0,losses:1,points:3}]
 await render(ObservationSeries,{series,flies})
 assert.equal(document.querySelectorAll('.series-conclusion').length,1)
 assert.match(document.body.textContent,/not natural aggression or general superiority/)
}))
test('saved observations recover from their endpoint and list owner records independently of match history',async()=>withDOM(async({render})=>{
 const calls=[];globalThis.fetch=async url=>{calls.push(String(url));return {ok:true,json:async()=>String(url).includes('?owner=')?[observationFixture(),{...observationFixture(),id:'other',owner:'other'}]:observationFixture()}}
 await render(ArenaObservations,{observationId:readRoute(location.hash).observation,identity:{id:'me'},flies})
 assert.ok(calls.includes('/api/v1/observation-series/series-1'));assert.ok(calls.includes('/api/v1/observation-series?owner=me'))
 const list=document.querySelector('[aria-label="Your recent observation series"]')
 assert.equal(list.querySelectorAll('a').length,1);assert.equal(list.querySelector('a').getAttribute('href'),'#tab=arena&observation=series-1')
}))
test('switching observation IDs discards late responses and exposes retrieval failures',async()=>withDOM(async({render})=>{
 let resolveOld;globalThis.fetch=async url=>String(url).endsWith('/series-1')?new Promise(resolve=>{resolveOld=resolve}):{ok:false,json:async()=>({detail:'Synthetic not found'})}
 await render(ArenaObservations,{observationId:'series-1',identity:null,flies})
 await render(ArenaObservations,{observationId:'absent',identity:null,flies})
 await act(async()=>resolveOld({ok:true,json:async()=>observationFixture('complete')}))
 assert.match(document.body.textContent,/Synthetic not found/);assert.doesNotMatch(document.body.textContent,/Synthetic fixture/)
}))
test('observation evidence and failure strings are bilingual in the duel module',async()=>withDOM(async({render})=>{
 for(const [key,value]of Object.entries(duelMessages).filter(([key])=>key.startsWith('observation.'))){assert.ok(value.en,key);assert.ok(value['zh-CN'],key)}
 localStorage.setItem('flyarena.locale','zh-CN')
 await render(ObservationSeries,{series:observationFixture('incomplete'),flies})
 assert.match(document.body.textContent,/观察系列报告/);assert.match(document.body.textContent,/无得分、胜者或排名/);assert.doesNotMatch(document.body.textContent,/observation\./)
}))

test('question controls only prefill editable conditions and never submit without the final action',async()=>withDOM(async({render})=>{
 const {ExperimentSetup}=require('./src/features/arena/ExperimentSetupPanel.js')
 const spec={connectome_sha256:'a'.repeat(64),model_profile:'malecns-lif-cpu-v1'},subject={id:'a'.repeat(32),name:'Fixture design',spec},wt={id:'b'.repeat(32),name:'Fixture WT',spec,reference_kind:'wildtype'}
 const maps=[{id:'scarcity',name:'Scarcity',english:'Scarcity',modes:['forage','contest']},{id:'duel',name:'Duel',english:'Duel',modes:['duel']},{id:'labyrinth',name:'Labyrinth',english:'Labyrinth',modes:['forage']}],submitted=[]
 function Harness(){
  const [selected,setSelected]=React.useState(subject.id),[opponent,setOpponent]=React.useState(''),[mode,setMode]=React.useState('forage'),[mapId,setMapId]=React.useState(''),[seedText,setSeedText]=React.useState('0'),[duration,setDuration]=React.useState(2),[bridgeProfile,setBridgeProfile]=React.useState('legacy-v1'),[sensoryProfile,setSensoryProfile]=React.useState('odor-only-v1')
  return React.createElement(ExperimentSetup,{flies:[subject,wt],maps,identity:null,season:{match_profiles:[{id:'legacy-v1',ready:true}]},selected,setSelected,opponent,setOpponent,mode,setMode,mapId,setMapId,seedText,setSeedText,duration,setDuration,bridgeProfile,setBridgeProfile,sensoryProfile,setSensoryProfile,busy:'',startMatch:async plan=>submitted.push(plan),onPreview:()=>{}})
 }
 await render(Harness,{})
 const click=async label=>act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent===label).click())
 const question=async id=>act(async()=>document.querySelector('[aria-labelledby="preset-'+id+'"] button').click())
 await question('scarcity')
 assert.equal(submitted.length,0);assert.equal(document.querySelector('#experiment-opponent').value,wt.id)
 assert.match(document.querySelector('.experiment-plan').textContent,/4 matches · 5 simulated seconds per match/)
 await question('maze')
 assert.equal(submitted.length,0);assert.equal(document.querySelector('#experiment-intent').value,'forage')
 assert.equal(document.querySelector('#experiment-opponent'),null)
 const duration=document.querySelector('select[aria-label="Duration"]')
 assert.ok(duration)
 await act(async()=>{duration.value='60';duration.dispatchEvent(new window.Event('change',{bubbles:true}))})
 await click('Run my simulation')
 assert.equal(submitted.length,1);assert.equal(submitted[0].matches.length,3)
 assert.equal(submitted[0].submissions[0].endpoint,'/observation-series');assert.ok(submitted[0].matches.every(m=>m.duration_seconds===60))
}))
