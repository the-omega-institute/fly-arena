import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'

const adapterOut=fs.mkdtempSync(path.join(os.tmpdir(),'probe-scene-'))
fs.writeFileSync(path.join(adapterOut,'package.json'),'{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(new URL('../node_modules',import.meta.url)),path.join(adapterOut,'node_modules'))
for(const folder of ['arena','phenotype'])fs.mkdirSync(path.join(adapterOut,folder))
for(const file of ['arena/obstacleGeometry','phenotype/probeScene']){
 const source=fs.readFileSync(new URL('../src/features/'+file+'.ts',import.meta.url),'utf8')
 fs.writeFileSync(path.join(adapterOut,file+'.js'),ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText)
}
const {probeGeometry,probeSegments,probeSampleAt,adaptProbeScene,probeFraming}=await import(path.join(adapterOut,'phenotype/probeScene.js'))
test.after(()=>fs.rmSync(adapterOut,{recursive:true,force:true}))
// Synthetic inputs exercise rendering contracts, not measured biological results.
const subjects=['wildtype','official','design'].map(role=>({role,fly_id:role,artifact_id:role+'-artifact',name:role}))
const scene={size:80,spawns:[[0,0,Math.PI/2]],obstacles:[{position:[10,0,1.5],size:[1,5,3]}],food:[{id:'test-food',position:[7,5,.15],initial:10}]}
const points=[{time:0,x:0,y:0,yaw:Math.PI*.95},{time:1,x:2,y:4,yaw:-Math.PI*.95},{time:3,x:6,y:8,yaw:0}]
const reports=subjects.map(s=>({...s,seed:42,status:'complete',duration_seconds:3,scene,trajectory:points}))

test('scene adapter retains recorded dimensions, food, and spawn yaw without mutation',()=>{
 const before=structuredClone(scene),result=probeGeometry(scene)
 assert.deepEqual(result,scene);assert.deepEqual(scene,before)
 assert.notEqual(result.obstacles[0].position,scene.obstacles[0].position)
 const shaped={...scene,obstacles:[{...scene.obstacles[0],shape:'ellipsoid',quaternion:[.5,.5,.5,.5],material:'leaf',color:'#123456'}]}
 assert.deepEqual(probeGeometry(shaped),shaped)
 assert.deepEqual(probeGeometry({...scene,food:[],obstacles:[],spawns:[]}),{...scene,food:[],obstacles:[],spawns:[]})
})
test('missing, malformed, and incomplete geometry stays unavailable',()=>{
 for(const value of [null,{}, {...scene,size:0},{...scene,size:NaN},{...scene,spawns:undefined},{...scene,obstacles:undefined},{...scene,food:null},{...scene,obstacles:[{position:[1,2],size:[1,2,3]}]},{...scene,obstacles:[{position:[1,2,3],size:[1,0,3]}]},{...scene,obstacles:[{...scene.obstacles[0],quaternion:[0,0,0,0]}]},{...scene,obstacles:[{...scene.obstacles[0],shape:'invented'}]},{...scene,food:[{...scene.food[0],position:[1,2,Infinity]}]},{...scene,spawns:[[0,0]]}])assert.equal(probeGeometry(value),null)
 const old=adaptProbeScene([{...reports[0],scene:undefined,geometry:{size:80}}],subjects,42)
 assert.equal(old.geometry,null);assert.equal(old.reason,'missing')
})
test('all roles use the selected seed and exact frozen fly/artifact identity',()=>{
 const foreign={...reports[0],artifact_id:'other',scene:{...scene,size:4}}
 const otherSeed=reports.map(r=>({...r,seed:43,trajectory:points.map(p=>({...p,x:100+p.x}))}))
 const result=adaptProbeScene([foreign,...otherSeed,...reports],subjects,42)
 assert.equal(result.reason,null);assert.equal(result.tracks.length,3)
 for(let i=0;i<3;i++){assert.equal(result.tracks[i].subject,subjects[i]);assert.deepEqual(result.tracks[i].segments,[points])}
 assert.equal(adaptProbeScene([...reports,...otherSeed],subjects,43).tracks[0].segments[0][0].x,100)
 assert.equal(adaptProbeScene(reports,subjects,99).geometry,null)
 assert.equal(adaptProbeScene([foreign],subjects,42).tracks[0].segments.length,0)
})
test('conflicting, invalid, missing, or duplicate report geometry cannot claim one 3D world',()=>{
 assert.equal(adaptProbeScene([reports[0],{...reports[1],scene:{...scene,size:81}}],subjects,42).reason,'conflict')
 assert.equal(adaptProbeScene([reports[0],{...reports[1],scene:{...scene,food:undefined}}],subjects,42).reason,'invalid')
 assert.equal(adaptProbeScene([reports[0],{...reports[1],scene:undefined}],subjects,42).reason,'missing')
 const duplicate=adaptProbeScene([...reports,reports[0]],subjects,42)
 assert.equal(duplicate.reason,'conflict');assert.equal(duplicate.tracks[0].invalid,true);assert.deepEqual(duplicate.tracks[0].segments,[])
})
test('failed and partial records retain their status, samples, and uncovered time',()=>{
 const partial=adaptProbeScene([{...reports[0],status:'failed',trajectory:points.slice(0,2)},reports[1]],subjects,42)
 assert.equal(partial.tracks[0].status,'failed');assert.deepEqual(partial.tracks[0].segments,[points.slice(0,2)])
 assert.equal(probeSampleAt(partial.tracks[0].segments,2),null)
 assert.equal(partial.tracks[2].status,'Unavailable');assert.deepEqual(partial.tracks[2].segments,[])
})
test('shared time interpolates x/y and shortest-arc yaw, preserving exact samples',()=>{
 const {segments}=probeSegments(points,3)
 assert.equal(probeSampleAt(segments,0).yaw,points[0].yaw)
 assert.equal(probeSampleAt(segments,1).yaw,points[1].yaw)
 const mid=probeSampleAt(segments,.5)
 assert.equal(mid.x,1);assert.equal(mid.y,2);assert.ok(Math.abs(mid.yaw-Math.PI)<1e-10)
 assert.deepEqual(Object.keys(mid).sort(),['time','x','y','yaw'])
 assert.equal(probeSampleAt(segments,2).x,4)
 assert.deepEqual(probeSampleAt(segments,3),points[2])
 for(const t of [-1,3.01,NaN,Infinity])assert.equal(probeSampleAt(segments,t),null)
 assert.equal(probeSampleAt([[points[1]]],1),points[1]);assert.equal(probeSampleAt([[points[1]]],1.1),null)
})
test('invalid samples leave gaps and never generate missing yaw or bridge invalid positions',()=>{
 for(const invalid of [{...points[1],x:NaN},{...points[1],yaw:undefined},null]){
  const result=probeSegments([points[0],invalid,points[2]],3)
  assert.equal(result.invalid,true);assert.deepEqual(result.segments,[[points[0]],[points[2]]])
  assert.equal(probeSampleAt(result.segments,1.5),null)
 }
 assert.equal(probeSegments([{...points[0],time:-1},...points],3).invalid,true)
 assert.deepEqual(probeSegments(points,1).segments,[points.slice(0,2)])
 for(const bad of [[points[1],points[0]],[points[0],points[0]]])assert.deepEqual(probeSegments(bad,3),{segments:[],invalid:true})
})
test('camera includes arena and outlying recorded positions; spawn yaw is not elevation',()=>{
 const {geometry,tracks}=adaptProbeScene(reports,subjects,42),framing=probeFraming(geometry,tracks)
 assert.equal(framing.span,80);assert.deepEqual(framing.target,[0,0,0]);assert.ok(framing.position[2]>40)
 const tilted=probeFraming({...geometry,spawns:[[0,0,99999]]},tracks)
 assert.deepEqual(tilted,framing)
 const far=adaptProbeScene(reports.map(r=>({...r,trajectory:[{...points[0],x:200,y:-100}]})),subjects,42)
 const wide=probeFraming(far.geometry,far.tracks)
 assert.ok(wide.span>=240);assert.deepEqual(wide.target,[80,-30,0])
})

// Exercise real view controls; mock only the GPU boundary, never the adapter or clock.
const {createRequire}=await import('node:module'),{default:React,act}=await import('react'),{createRoot}=await import('react-dom/client'),{JSDOM}=await import('jsdom')
const web=new URL('../',import.meta.url).pathname,out=fs.mkdtempSync(path.join(os.tmpdir(),'probe-controls-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web,'node_modules')),path.join(out,'node_modules'))
for(const relative of ['src/shared/SceneAvailability.tsx','src/shared/messages/scene.ts','src/features/arena/obstacleGeometry.ts','src/features/phenotype/ProbeScene3D.tsx','src/features/phenotype/probeScene.ts','src/shared/research.ts','src/shared/theme.ts','src/shared/messages/lab3d.ts']){
 const dest=path.join(out,relative.replace(/\.tsx?$/,'.js'));fs.mkdirSync(path.dirname(dest),{recursive:true})
 fs.writeFileSync(dest,ts.transpileModule(fs.readFileSync(path.join(web,relative),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText)
}
fs.writeFileSync(path.join(out,'src/features/phenotype/probeScene.css'),'')
fs.writeFileSync(path.join(out,'src/shared/sceneAvailability.css'),'')
fs.mkdirSync(path.join(out,'src/features/arena'),{recursive:true})
fs.writeFileSync(path.join(out,'src/features/arena/Habitat.js'),'exports.Habitat=()=>null')
fs.writeFileSync(path.join(out,'src/shared/i18n.js'),"const {lab3dMessages}=require('./messages/lab3d'); const {sceneMessages}=require('./messages/scene'); exports.useI18n=()=>({resolved:'dark',t:key=>(sceneMessages[key]||lab3dMessages[key])?.[globalThis.probeTestLocale]||key})")
const require=createRequire(path.join(out,'package.json'));require.extensions['.css']=()=>{}
let canvasProps=null,canvasFailure=false,renderFrame=null
const canvasEvents=new EventTarget()
const fiberFile=require.resolve('@react-three/fiber')
const originalFiber=require.cache[fiberFile]
require.cache[fiberFile]={id:fiberFile,filename:fiberFile,loaded:true,exports:{Canvas:props=>{canvasProps=props;if(canvasFailure)throw Error('TEST renderer failure');return React.createElement('div',{'data-test-canvas':true},React.Children.toArray(props.children).find(child=>child.type?.name==='SceneRendererGuard'))},useThree:selector=>selector({gl:{domElement:canvasEvents,getContext:()=>({isContextLost:()=>false})}}),useFrame:fn=>{renderFrame=fn}}}
const {ProbeScene3D}=require('./src/features/phenotype/ProbeScene3D.js')
if(originalFiber)require.cache[fiberFile]=originalFiber;else delete require.cache[fiberFile]
const globalKeys=['window','document','navigator','IS_REACT_ACT_ENVIRONMENT','probeTestLocale']
const props={reports,subjects,seed:42,time:0,fallback:React.createElement('svg',{'data-plan':true})}
const button=text=>[...document.querySelectorAll('button')].find(b=>b.textContent===text)
let root=null,dom=null
async function mount(overrides={}){await act(async()=>root.render(React.createElement(ProbeScene3D,{...props,...overrides})))}
async function click(text){await act(async()=>button(text).click())}
async function withDom(fn){
 const originals=Object.fromEntries(globalKeys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 dom=new JSDOM('<!doctype html><main id="root"></main>',{url:'http://probe.test/'})
 try{
  for(const k of ['window','document','navigator'])Object.defineProperty(globalThis,k,{configurable:true,value:dom.window[k]})
  globalThis.IS_REACT_ACT_ENVIRONMENT=true;globalThis.probeTestLocale='en'
  dom.window.HTMLCanvasElement.prototype.getContext=()=>({getExtension:()=>({loseContext(){}})})
  root=createRoot(document.getElementById('root'));canvasProps=null;canvasFailure=false
  await fn()
 }finally{
  try{if(root)await act(async()=>root.unmount())}finally{
   dom.window.close();root=null;dom=null;canvasProps=null;canvasFailure=false
   for(const [k,d]of Object.entries(originals)){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k]}
  }
 }
}
const uiTest=(name,fn)=>test(name,{concurrency:false},()=>withDom(fn))
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))

test('UI fixture restores global descriptors even when a mounted test fails',async()=>{
 const originals=globalKeys.map(k=>Object.getOwnPropertyDescriptor(globalThis,k))
 await assert.rejects(withDom(async()=>{await mount();throw Error('TEST assertion failure')}),/TEST assertion failure/)
 assert.deepEqual(globalKeys.map(k=>Object.getOwnPropertyDescriptor(globalThis,k)),originals)
 assert.equal(root,null);assert.equal(dom,null)
})

uiTest('view automatically falls back to the 2D slot when WebGL is absent',async()=>{
 await mount();assert.ok(document.querySelector('[data-plan]'));assert.equal(button('3D').disabled,true)
 assert.equal(button('2D plan').getAttribute('aria-pressed'),'true');assert.match(document.body.textContent,/WebGL unavailable/)
 assert.equal(canvasProps,null)
})
uiTest('3D toggle and selected seed use the external shared clock without resetting it',async()=>{
 dom.window.WebGL2RenderingContext=class {}
 await mount();assert.ok(document.querySelector('[data-test-canvas]'));assert.equal(button('3D').getAttribute('aria-pressed'),'true')
 assert.match(document.body.textContent,/Recorded planar trajectories/)
 const world=()=>React.Children.toArray(canvasProps.children).find(child=>child.type?.name==='ProbeWorld').props
 assert.equal(world().time,0);assert.equal(world().tracks.length,3)
 await mount({time:1.5});assert.equal(world().time,1.5)
 assert.equal(probeSampleAt(world().tracks[0].segments,world().time).x,3)
 await click('2D plan');assert.ok(document.querySelector('[data-plan]'));assert.ok(!document.querySelector('[data-test-canvas]'))
 await click('3D');assert.equal(world().time,1.5)
 const later=reports.map(r=>({...r,seed:43,trajectory:points.map(p=>({...p,x:p.x+10}))}))
 await mount({reports:[...reports,...later],seed:43,time:1.5});assert.equal(world().tracks[0].segments[0][0].x,10)
 await mount({time:4});assert.equal(document.body.textContent.match(/No recorded position at shared time/g).length,3)
})
uiTest('missing or conflicting geometry cannot mount a 3D canvas and keeps failed status visible',async()=>{
 dom.window.WebGL2RenderingContext=class {}
 await mount({reports:[{...reports[0],scene:undefined,status:'failed'}]})
 assert.ok(document.querySelector('[data-plan]'));assert.equal(button('3D').disabled,true);assert.match(document.body.textContent,/geometry unavailable/);assert.match(document.body.textContent,/failed/)
 await mount({reports:[reports[0],{...reports[1],scene:{...scene,size:10}}]})
 assert.match(document.body.textContent,/geometry conflicts/);assert.equal(canvasProps,null)
})
uiTest('WebGL context loss falls back to 2D and preserves visible failure explanation',async()=>{
 dom.window.WebGL2RenderingContext=class {}
 await mount();await act(async()=>canvasEvents.dispatchEvent(new Event('webglcontextlost',{cancelable:true})))
 assert.ok(document.querySelector('[data-plan]'));assert.match(document.body.textContent,/WebGL context lost/);assert.equal(button('3D').disabled,true)
})
uiTest('renderer startup exceptions fall back to the plan without crashing the lab',async()=>{
 dom.window.WebGL2RenderingContext=class {};canvasFailure=true
 const original=console.error;console.error=()=>{}
 try{await mount()}finally{console.error=original}
 assert.ok(document.querySelector('[data-plan]'));assert.match(document.body.textContent,/renderer failed/)
})
uiTest('3D explanatory notes and fallback controls follow the Chinese catalog',async()=>{
 globalThis.probeTestLocale='zh-CN';dom.window.WebGL2RenderingContext=class {}
 await mount();assert.match(document.body.textContent,/已记录的平面轨迹/);assert.ok(button('2D 平面图'))
 await mount({reports:[]});assert.match(document.body.textContent,/探针几何记录不可用/)
})

uiTest('runtime rendering failure and retry preserve seed, time and failed report status',async()=>{
 dom.window.WebGL2RenderingContext=class {}
 const failedReports=reports.map(r=>({...r,seed:43,status:'failed'}))
 await mount({reports:failedReports,seed:43,time:1.5})
 await act(async()=>renderFrame({gl:{render(){throw Error('TEST frame failure')}},scene:{},camera:{}}))
 assert.ok(document.querySelector('[data-plan]'));assert.match(document.body.textContent,/renderer failed/);assert.match(document.body.textContent,/failed/)
 await click('Retry 3D')
 const world=React.Children.toArray(canvasProps.children).find(child=>child.type?.name==='ProbeWorld').props
 assert.equal(world.time,1.5);assert.deepEqual(world.tracks,adaptProbeScene(failedReports,subjects,43).tracks);assert.equal(world.tracks[0].status,'failed')
 assert.ok(document.querySelector('[data-test-canvas]'))
})
