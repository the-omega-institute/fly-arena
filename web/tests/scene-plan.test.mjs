import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createRequire} from 'node:module'
import ts from 'typescript'
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {renderToStaticMarkup} from 'react-dom/server'
import {JSDOM} from 'jsdom'

const web=new URL('../',import.meta.url).pathname,out=fs.mkdtempSync(path.join(os.tmpdir(),'scene-plan-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web,'node_modules')),path.join(out,'node_modules'))
for(const relative of ['ArenaCanvas.tsx','features/arena/ScenePlanView.tsx','features/arena/sceneProjection.ts','features/arena/obstacleGeometry.ts','features/arena/followCamera.ts','types.ts','shared/theme.ts','shared/messages/scene.ts']){
 const dest=path.join(out,'src',relative.replace(/\.tsx?$/,'.js'));fs.mkdirSync(path.dirname(dest),{recursive:true})
 fs.writeFileSync(dest,ts.transpileModule(fs.readFileSync(path.join(web,'src',relative),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText)
}
fs.writeFileSync(path.join(out,'src/features/arena/scenePresentation.css'),'')
for(const name of ['ReplayCamera','ArenaWorldLabel','Habitat'])fs.writeFileSync(path.join(out,`src/features/arena/${name}.js`),`exports.${name}=()=>null`)
fs.writeFileSync(path.join(out,'src/features/arena/replayInspector.js'),'exports.replayLabelHidden=()=>false')
fs.writeFileSync(path.join(out,'src/shared/i18n.js'),"const {sceneMessages}=require('./messages/scene');exports.useI18n=()=>({resolved:'dark',t:key=>sceneMessages[key]?.[globalThis.sceneTestLocale||'en']||key})")
const require=createRequire(path.join(out,'package.json'));require.extensions['.css']=()=>{}
let canvasProps,canvasFailure,renderFrame,canvasEvents
const fiberFile=require.resolve('@react-three/fiber'),dreiFile=require.resolve('@react-three/drei')
require.cache[fiberFile]={id:fiberFile,filename:fiberFile,loaded:true,exports:{Canvas:props=>{canvasProps=props;if(canvasFailure)throw Error('TEST renderer startup');return React.createElement('div',{'data-canvas':true},React.Children.toArray(props.children).find(child=>child.type?.name==='ArenaRendererGuard'))},useThree:selector=>selector({gl:{domElement:canvasEvents}}),useFrame:fn=>{renderFrame=fn}}}
require.cache[dreiFile]={id:dreiFile,filename:dreiFile,loaded:true,exports:{}}
const {projectObstacle,planPosition,planTrails,planFood,planBounds,planDefault,validPlanWorld}=require('./src/features/arena/sceneProjection.js')
const {ScenePlanView}=require('./src/features/arena/ScenePlanView.js'),{ArenaCanvas}=require('./src/ArenaCanvas.js')
const {sceneMessages}=require('./src/shared/messages/scene.js')
const fixture=JSON.parse(fs.readFileSync(new URL('../../tests/fixtures/geometry_contract.json',import.meta.url)))
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`)
const frame=(time,positions,food)=>({time,tick:time,positions,food,poses:[]})
const frames=[frame(0,[[0,0,1]],[8]),frame(1,[[2,4,1]],[4]),frame(2,[[4,8,1]],[0])]
const world={id:'orchard',size:20,obstacles:[{position:[2,3,1],size:[2,4,2]}],food:[{id:'food-0',position:[4,2,.2],initial:8}],spawns:[[-4,1,Math.PI/2]],flies:[{id:'a',name:'Recorded fly',color:'mint'}],body:{meshes:{},geoms:[]}}
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))

test('box footprints preserve yaw, full sizes, and tilted projected height',()=>{
 const q=[Math.SQRT1_2,0,0,Math.SQRT1_2],box=projectObstacle({position:[3,4,5],size:[2,6,4],quaternion:q})
 assert.equal(box.shape,'box');assert.equal(box.points.length,4)
 close(Math.min(...box.points.map(p=>p[0])),0);close(Math.max(...box.points.map(p=>p[0])),6)
 close(Math.min(...box.points.map(p=>p[1])),3);close(Math.max(...box.points.map(p=>p[1])),5)
 const tilted=projectObstacle({position:[0,0,0],size:[2,6,4],quaternion:[Math.cos(Math.PI/8),0,Math.sin(Math.PI/8),0]})
 close(Math.max(...tilted.points.map(p=>p[0])),3/Math.sqrt(2))
})
test('ellipsoid silhouettes use all three rotated axes rather than a yaw-only approximation',()=>{
 const shape=projectObstacle({position:[3,4,5],size:[8,2,4],quaternion:[Math.cos(Math.PI/8),0,Math.sin(Math.PI/8),0],shape:'ellipsoid'})
 assert.equal(shape.shape,'ellipsoid');assert.deepEqual(shape.center,[3,4]);close(shape.rx,Math.sqrt(10));close(shape.ry,1);close(shape.angle,0)
 const yaw=projectObstacle({position:[0,0,0],size:[8,2,4],quaternion:[Math.cos(Math.PI/8),0,0,Math.sin(Math.PI/8)],shape:'ellipsoid'})
 close(yaw.rx,4);close(yaw.ry,1);close(yaw.angle,45)
})
test('all recorded geometry fixtures project without mutation and invalid geometry remains unavailable',()=>{
 for(const maps of Object.values(fixture.maps))for(const scene of Object.values(maps)){
  const before=structuredClone(scene);assert.ok(validPlanWorld(scene))
  for(const obstacle of scene.obstacles){const p=projectObstacle(obstacle);assert.ok(p.shape==='box'?p.points.flat().every(Number.isFinite):[p.rx,p.ry,p.angle].every(Number.isFinite))}
  assert.deepEqual(scene,before)
 }
 for(const obstacle of fixture.invalid_obstacles)assert.equal(validPlanWorld({...world,obstacles:[obstacle]}),false)
 assert.equal(validPlanWorld(null),false)
 assert.equal(validPlanWorld({...world,food:[null]}),false)
})
test('plan positions and elapsed trails share interpolation, exclude future samples, and preserve gaps',()=>{
 assert.deepEqual(planPosition(frames[0],frames[1],.5,0),[1,2])
 assert.deepEqual(planTrails(frames,0,.5),[[[0,0],[1,2]]])
 assert.deepEqual(planTrails(frames,0,0),[[[0,0]]]);assert.deepEqual(planTrails(frames,0,-1),[])
 for(const positions of [[],[null],[[NaN,1]],[[1,Infinity]],[[1,1,NaN]]]){
  const missing=frame(1,positions)
  assert.equal(planPosition(frames[0],missing,.5,0),null)
  assert.equal(planPosition(missing,frames[2],.5,0),null)
  assert.deepEqual(planPosition(missing,frames[2],1,0),[4,8])
  assert.deepEqual(planTrails([frames[0],missing,frames[2]],0,2),[[[0,0]],[[4,8]]])
 }
 assert.equal(planPosition(frame(NaN,[[0,0,0]]),frames[1],0,0),null)
 assert.equal(planPosition(frames[0],frame(Infinity,[[1,1,1]]),.5,0),null)
 assert.equal(planPosition(frames[0],undefined,.5,0),null)
 assert.deepEqual(planTrails(frames,3,2),[])
})
test('food preserves zero and missing values without substituting initial food for replay gaps',()=>{
 assert.equal(planFood(world.food[0],0,true,frames[2]),0)
 for(const food of [undefined,[],[null],[NaN],[-1]])assert.equal(planFood(world.food[0],0,true,frame(1,[],food)),null)
 assert.equal(planFood(world.food[0],0,false),8)
 assert.equal(planFood(world.food[0],0,true),null)
})
test('view defaults and bounds use actual recorded metadata, including outlying positions and spawns',()=>{
 for(const id of ['maze','labyrinth','switchback'])assert.equal(planDefault({...world,id}),'2d')
 assert.equal(planDefault(world),'3d');assert.equal(planDefault({...world,id:undefined,task:{id:'maze-arrival-v1'}}),'2d')
 const bounds=planBounds({...world,spawns:[[30,0,10000]]},[frame(0,[[-40,50,1]])])
 assert.ok(bounds[0]<-40&&bounds[1]<-50&&bounds[0]+bounds[2]>30);assert.ok(bounds[3]<100)
})
test('SVG shows modeled versus recorded provenance, unknown food, and absent positions without invented headings',()=>{
 const html=renderToStaticMarkup(React.createElement(ScenePlanView,{world,recorded:true,frame:frame(1,[]),frames}))
 assert.match(html,/Recorded geometry and trails/);assert.match(html,/data-amount="unrecorded"/);assert.match(html,/No recorded position/)
 assert.doesNotMatch(html,/data-position-slot/);assert.match(html,/rotate\(-90\)/)
 const preview=renderToStaticMarkup(React.createElement(ScenePlanView,{world:{...world,flies:[]}}))
 assert.match(preview,/Modeled layout/);assert.match(preview,/data-amount="8"/)
})
test('new UI catalog entries have English and Chinese text',()=>{
 for(const [key,value] of Object.entries(sceneMessages)){assert.ok(value.en,key);assert.ok(value['zh-CN'],key)}
})

async function withDom(fn){
 const keys=['window','document','IS_REACT_ACT_ENVIRONMENT','sceneTestLocale'],originals=Object.fromEntries(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 const dom=new JSDOM('<main id="root"></main>');let root
 try{
  for(const [key,value] of Object.entries({window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true,sceneTestLocale:'en'}))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value})
  dom.window.HTMLCanvasElement.prototype.getContext=()=>({getExtension:()=>null})
  canvasProps=null;canvasFailure=false;renderFrame=null;canvasEvents=new dom.window.EventTarget()
  root=createRoot(document.getElementById('root'))
  const mount=async(props={})=>act(async()=>root.render(React.createElement(ArenaCanvas,{scene:world,frames,frame:frames[0],next:frames[1],alpha:0,...props})))
  const button=name=>[...document.querySelectorAll('button')].find(b=>b.textContent===name)
  const click=async name=>act(async()=>button(name).dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true})))
  await fn({dom,mount,button,click})
 }finally{
  try{if(root)await act(async()=>root.unmount())}finally{dom.window.close();for(const [k,d]of Object.entries(originals)){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k]}}
 }
}
const uiTest=(name,fn)=>test(name,{concurrency:false},()=>withDom(fn))
uiTest('missing WebGL automatically shows a usable plan and visible explanation',async({mount,button})=>{
 await mount();assert.ok(document.querySelector('svg.scene-plan'));assert.equal(button('3D').disabled,true);assert.equal(button('2D plan').getAttribute('aria-pressed'),'true');assert.match(document.body.textContent,/WebGL unavailable/);assert.equal(canvasProps,null)
})
uiTest('manual toggles preserve the external clock and selected position; map changes restore their default',async({dom,mount,button,click})=>{
 dom.window.WebGL2RenderingContext=class {}
 await mount();assert.ok(document.querySelector('[data-canvas]'));assert.equal(button('3D').getAttribute('aria-pressed'),'true')
 await click('2D plan');await mount({alpha:.5});assert.equal(document.querySelector('[data-position-slot="0"]').getAttribute('transform'),'translate(1 -2)')
 await click('3D');const scene=React.Children.toArray(canvasProps.children).find(child=>child.type?.name==='ArenaScene');assert.equal(scene.props.alpha,.5)
 await mount({scene:{...world,id:'switchback'}});assert.ok(document.querySelector('svg.scene-plan'));assert.equal(button('2D plan').getAttribute('aria-pressed'),'true')
})
uiTest('maze, labyrinth and switchback previews default to plan with configured spawns and no recorded movement',async({dom,mount,button})=>{
 dom.window.WebGL2RenderingContext=class {}
 for(const id of ['maze','labyrinth','switchback']){await mount({scene:null,layout:{...world,id,flies:[]},frame:undefined,frames:[]});assert.equal(button('2D plan').getAttribute('aria-pressed'),'true');assert.match(document.body.textContent,/Modeled layout/);assert.ok(document.querySelector('.scene-plan-spawn'))}
})
uiTest('context loss falls back, retains the current clock, and explains why',async({dom,mount,button})=>{
 dom.window.WebGL2RenderingContext=class {};await mount({alpha:.5})
 const event=new dom.window.Event('webglcontextlost',{cancelable:true});await act(async()=>canvasEvents.dispatchEvent(event))
 assert.ok(event.defaultPrevented);assert.equal(button('3D').disabled,true);assert.match(document.body.textContent,/context lost/)
 assert.equal(document.querySelector('[data-position-slot="0"]').getAttribute('transform'),'translate(1 -2)')
})
uiTest('renderer startup exceptions fall back with explanation',async({dom,mount,button})=>{
 dom.window.WebGL2RenderingContext=class {};canvasFailure=true
 const error=console.error;console.error=()=>{};try{await mount()}finally{console.error=error}
 assert.ok(document.querySelector('svg.scene-plan'));assert.match(document.body.textContent,/renderer failed/);assert.equal(button('3D').disabled,true)
})
uiTest('runtime rendering exceptions are caught outside the React render boundary',async({dom,mount})=>{
 dom.window.WebGL2RenderingContext=class {};await mount()
 await act(async()=>renderFrame({gl:{render(){throw Error('TEST GPU frame failure')}},scene:{},camera:{}}))
 assert.ok(document.querySelector('svg.scene-plan'));assert.match(document.body.textContent,/renderer failed/)
})
uiTest('Chinese controls and failure notes come from the scene module',async({mount,button})=>{
 globalThis.sceneTestLocale='zh-CN';await mount();assert.ok(button('2D 平面图'));assert.match(document.body.textContent,/WebGL 不可用/);assert.match(document.body.textContent,/已记录的几何与轨迹/)
})
