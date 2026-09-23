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

const web=new URL('../',import.meta.url).pathname,out=fs.mkdtempSync(path.join(os.tmpdir(),'map-purpose-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web,'node_modules')),path.join(out,'node_modules'))
for(const relative of ['src/api.ts','src/shared/i18n.tsx','src/shared/messages.ts','src/features/arena/mapPurpose.ts','src/features/arena/MapPreview.tsx',...fs.readdirSync(path.join(web,'src/shared/messages')).filter(f=>f.endsWith('.ts')).map(f=>'src/shared/messages/'+f)]){
 const result=ts.transpileModule(fs.readFileSync(path.join(web,relative),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}})
 const dest=path.join(out,relative.replace(/\.tsx?$/,'.js'));fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,result.outputText)
}
// Only WebGL is stubbed; the preview, API client, legend and translations are real.
fs.writeFileSync(path.join(out,'src/ArenaCanvas.js'),'exports.ArenaCanvas=()=>null')
const require=createRequire(path.join(out,'package.json'))
const {mapPurpose}=require('./src/features/arena/mapPurpose.js')
const {MapPreview,MapPurposeLegend}=require('./src/features/arena/MapPreview.js')
const {I18nProvider}=require('./src/shared/i18n.js')
const {mapsMessages}=require('./src/shared/messages/maps.js')
const dom=new JSDOM('<!doctype html><html><body><main id="root"></main></body></html>',{url:'http://arena.example/'})
const originals=Object.fromEntries(['window','document','navigator','localStorage','matchMedia','IS_REACT_ACT_ENVIRONMENT','fetch'].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
for(const k of ['window','document','navigator','localStorage'])Object.defineProperty(globalThis,k,{configurable:true,value:dom.window[k]})
globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}})
globalThis.IS_REACT_ACT_ENVIRONMENT=true
let root=createRoot(document.getElementById('root'))
const limitation='Long-horizon locomotion inversion remains unresolved (issue #82); arrival time is not a valid optimization target yet.'
// Synthetic API fixtures exercise presentation contracts; they are not run evidence.
const layout={id:'labyrinth',size:32,spawns:[[-11,-10,0],[11,10,Math.PI]],food:[{id:'food-0',position:[10.1,9.8,.15],initial:10}],obstacles:[{position:[-14,0,2.5],size:[1,29,5]}],modes:['forage'],metadata:{supported_modes:['forage'],recommended_horizon_seconds:{min:30,max:180},purpose:'Exploratory maze traversal and first physical mouth contact with the goal food.',scientific_status:'observation-only',status_reason:limitation}}
const props={mapId:'labyrinth',seed:42,bridgeProfile:'legacy-v1',participants:[]}
const text=()=>document.body.textContent
async function mount(Component,props){await act(async()=>root.render(React.createElement(I18nProvider,null,React.createElement(Component,props))))}
test.afterEach(async()=>{await act(async()=>root.unmount());document.getElementById('root').replaceChildren();root=createRoot(document.getElementById('root'));localStorage.clear()})
test.after(async()=>{await act(async()=>root.unmount());dom.window.close();fs.rmSync(out,{recursive:true,force:true});for(const [k,d]of Object.entries(originals)){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k]}})

test('legend uses returned geometry rather than map identity or active contestants',()=>{
 const frozen=JSON.stringify(layout),legend=mapPurpose(layout)
 assert.equal(legend.spawnSlots,2);assert.equal(legend.foodCount,1);assert.equal(legend.obstacleCount,1);assert.equal(legend.sizeMm,32)
 assert.deepEqual(legend.modes,['Solo forage']);assert.equal(legend.horizon,'30–180');assert.equal(legend.limitation,limitation)
 const changed=mapPurpose({...layout,food:[],spawns:[layout.spawns[0]],obstacles:[...layout.obstacles,...layout.obstacles],size:18})
 assert.equal(changed.foodCount,0);assert.equal(changed.spawnSlots,1);assert.equal(changed.obstacleCount,2);assert.equal(changed.sizeMm,18)
 assert.equal(JSON.stringify(layout),frozen)
})

test('old or incomplete responses preserve unknowns and never imply qualification',()=>{
 const legacy=mapPurpose({size:28,food:[],obstacles:[],modes:['contest']})
 assert.equal(legacy.foodCount,0);assert.equal(legacy.obstacleCount,0);assert.equal(legacy.spawnSlots,null)
 assert.deepEqual(legacy.modes,['Two-fly food competition']);assert.equal(legacy.status,'Scientific status unavailable');assert.equal(legacy.horizon,null)
 assert.equal(mapPurpose({}).foodCount,null);assert.equal(mapPurpose({size:NaN}).sizeMm,null)
 assert.equal(mapPurpose({...layout,metadata:{...layout.metadata,scientific_status:'future-status'}}).status,'Scientific status unavailable')
 assert.equal(mapPurpose({...layout,metadata:{...layout.metadata,recommended_horizon_seconds:{min:30,max:2}}}).horizon,null)
})

test('mode labels keep ring contests distinct from contact territory',()=>{
 const legend=mapPurpose({...layout,metadata:{...layout.metadata,supported_modes:['forage','contest','sumo','duel','future-mode']}})
 assert.deepEqual(legend.modes,['Solo forage','Two-fly food competition','Contact ring contest','Contact / territory','future-mode'])
})

test('English legend exposes layout counts, exploratory horizon and arrival limitation',async()=>{
 localStorage.setItem('flyarena.locale','en')
 await mount(MapPurposeLegend,{layout})
 assert.match(text(),/Spawn slots: 2/);assert.match(text(),/Food patches: 1/);assert.match(text(),/Solid obstacles: 1/);assert.match(text(),/32 × 32 mm/)
 assert.match(text(),/30–180 simulated seconds/);assert.match(text(),/issue #82/);assert.match(text(),/arrival time is not a valid optimization target yet/)
 assert.match(text(),/Modeled seeded layout, not a recorded run/)
 assert.equal(document.querySelector('[data-scientific-status]').textContent,'Observation only')
})

test('Chinese legend translates purpose, status, modes and scientific limitation',async()=>{
 localStorage.setItem('flyarena.locale','zh-CN')
 await mount(MapPurposeLegend,{layout})
 assert.match(text(),/出生位置数: 2/);assert.match(text(),/单蝇觅食/);assert.match(text(),/仅供观测/);assert.match(text(),/长时程运动倒置/);assert.match(text(),/到达时间尚不能作为有效的优化目标/)
 assert.ok(text().includes(mapsMessages[layout.metadata.purpose]['zh-CN']))
 assert.doesNotMatch(text(),/Scientific status|Solo forage|Long-horizon/)
})

test('missing metadata stays visible while actual zero geometry counts remain usable',async()=>{
 localStorage.setItem('flyarena.locale','en')
 await mount(MapPurposeLegend,{layout:{...layout,metadata:undefined,food:[],obstacles:[]}})
 assert.match(text(),/Food patches: 0/);assert.match(text(),/Solid obstacles: 0/)
 assert.match(text(),/Scientific status unavailable/);assert.match(text(),/Map suitability metadata is unavailable on this server/)
 assert.doesNotMatch(text(),/Suggested observation horizon/)
})

test('switching seed and profile hides the prior legend until the matching layout arrives',async()=>{
 localStorage.setItem('flyarena.locale','en')
 const pending=[]
 globalThis.fetch=(url,options)=>new Promise(resolve=>pending.push({url,options,resolve}))
 await mount(MapPreview,props)
 assert.match(text(),/Loading map/)
 await act(async()=>pending[0].resolve({ok:true,json:async()=>layout}))
 assert.match(text(),/Food patches: 1/)
 await mount(MapPreview,{...props,seed:91,bridgeProfile:'sensorimotor-research-v2'})
 assert.match(text(),/Loading map/);assert.doesNotMatch(text(),/Food patches/)
 assert.match(pending[1].url,/seed=91&bridge_profile=sensorimotor-research-v2/)
 await mount(MapPreview,{...props,mapId:'blank',seed:92})
 assert.equal(pending[1].options.signal.aborted,true)
 await act(async()=>pending[1].resolve({ok:true,json:async()=>layout}))
 assert.match(text(),/Loading map/);assert.doesNotMatch(text(),/Food patches/)
 await act(async()=>pending[2].resolve({ok:true,json:async()=>({...layout,id:'blank',food:[],obstacles:[],metadata:undefined})}))
 assert.match(text(),/Food patches: 0/);assert.match(text(),/Scientific status unavailable/)
})

test('preview request failures remain visible instead of showing stale suitability',async()=>{
 localStorage.setItem('flyarena.locale','en')
 globalThis.fetch=async()=>({ok:false,status:503,json:async()=>({detail:'Preview service unavailable'})})
 await mount(MapPreview,props)
 assert.match(text(),/Map preview unavailable/);assert.match(text(),/Preview service unavailable/)
 assert.equal(document.querySelector('[data-scientific-status]'),null)
})
