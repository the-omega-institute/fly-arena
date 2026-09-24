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

const web=new URL('../',import.meta.url).pathname,out=fs.mkdtempSync(path.join(os.tmpdir(),'scene-availability-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web,'node_modules')),path.join(out,'node_modules'))
for(const relative of ['shared/SceneAvailability.tsx','shared/messages/scene.ts',...['AnatomicalBrain','AnatomicalBrainCanvas','MorphologyCanvas','LocalBrainGraph','NeuronActivityTrace','BrainEventLens'].map(n=>'features/arena/'+n+'.tsx'),...['anatomy','morphology','brainResponse'].map(n=>'features/arena/'+n+'.ts')]){
 const dest=path.join(out,'src',relative.replace(/\.tsx?$/,'.js'));fs.mkdirSync(path.dirname(dest),{recursive:true})
 fs.writeFileSync(dest,ts.transpileModule(fs.readFileSync(path.join(web,'src',relative),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText)
}
fs.writeFileSync(path.join(out,'src/shared/sceneAvailability.css'),'')
fs.writeFileSync(path.join(out,'src/api.js'),'exports.serviceUrl=path=>path')
fs.writeFileSync(path.join(out,'src/shared/i18n.js'),"const {sceneMessages}=require('./messages/scene');exports.useI18n=()=>({locale:globalThis.sceneTestLocale,t:key=>sceneMessages[key]?.[globalThis.sceneTestLocale]||key})")
const require=createRequire(path.join(out,'package.json'));require.extensions['.css']=()=>{}
let canvasFailure=false,renderFrame,gl,canvasProps,factoryFailure=false,factoryOptions=null,startupResult=null,configureRenderer=false
// Only GPU rasterization is replaced. Real availability, graph, trace and loading
// code run against explicitly synthetic fixtures, not biological measurements.
function Canvas(props){
 canvasProps=props
 React.useEffect(()=>{if(configureRenderer)startupResult=props.gl({canvas:document.createElement('canvas')})},[props.gl])
 if(canvasFailure)throw Error('TEST renderer startup failure')
 return React.createElement('div',{'data-canvas':true},React.Children.toArray(props.children).find(child=>child.type?.name==='SceneRendererGuard'))
}
const fiberFile=require.resolve('@react-three/fiber'),dreiFile=require.resolve('@react-three/drei')
require.cache[fiberFile]={id:fiberFile,filename:fiberFile,loaded:true,exports:{Canvas,useThree:selector=>selector({gl}),useFrame:fn=>{renderFrame=fn}}}
require.cache[dreiFile]={id:dreiFile,filename:dreiFile,loaded:true,exports:{OrbitControls:()=>null}}
const threeFile=require.resolve('three'),originalThree=require(threeFile)
require.cache[threeFile]={id:threeFile,filename:threeFile,loaded:true,exports:{...originalThree,WebGLRenderer:class {constructor(options){factoryOptions=options;if(factoryFailure)throw Error('TEST async renderer construction');this.testRenderer=true}}}}
const {SceneAvailability}=require('./src/shared/SceneAvailability.js'),{AnatomicalBrain}=require('./src/features/arena/AnatomicalBrain.js')
const {sceneMessages}=require('./src/shared/messages/scene.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))

async function withDom(fn){
 const keys=['window','document','IS_REACT_ACT_ENVIRONMENT','sceneTestLocale','fetch'],originals=Object.fromEntries(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 const dom=new JSDOM('<main id="root"></main>');let root
 try{
  for(const [key,value] of Object.entries({window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true,sceneTestLocale:'en'}))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value})
  dom.window.WebGL2RenderingContext=class {}
  dom.window.HTMLCanvasElement.prototype.getContext=()=>({getExtension:()=>null})
  gl={domElement:new dom.window.EventTarget(),render(){},getContext:()=>({isContextLost:()=>false})};canvasFailure=false;renderFrame=null;canvasProps=null;factoryFailure=false;factoryOptions=null;startupResult=null;configureRenderer=false
  root=createRoot(document.getElementById('root'))
  const mount=async element=>act(async()=>root.render(element))
  const click=async text=>act(async()=>{const button=[...document.querySelectorAll('button')].find(b=>b.textContent.startsWith(text));assert.ok(button,text);button.click()})
  const lose=async()=>{const event=new dom.window.Event('webglcontextlost',{cancelable:true});await act(async()=>gl.domElement.dispatchEvent(event));assert.equal(event.defaultPrevented,true)}
  await fn({dom,root,mount,click,lose})
 }finally{
  try{if(root)await act(async()=>root.unmount())}finally{dom.window.close();for(const [k,d]of Object.entries(originals)){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k]}}
 }
}
const uiTest=(name,fn)=>test(name,{concurrency:false},()=>withDom(fn))
const fallback=React.createElement('svg',{'data-fallback':true})
const scene=(props={})=>React.createElement(SceneAvailability,{fallback,...props},(guard,renderer)=>React.createElement(Canvas,{gl:renderer},guard))
uiTest('missing API, null context and throwing context all provide an explanation, fallback and working retry',async({dom,mount,click})=>{
 for(const mode of ['missing','null','throw']){
  dom.window.WebGL2RenderingContext=mode==='missing'?undefined:class {}
  dom.window.HTMLCanvasElement.prototype.getContext=()=>{if(mode==='throw')throw Error('TEST denied context');return null}
  await mount(scene({key:mode}));assert.ok(document.querySelector('[data-fallback]'));assert.match(document.body.textContent,/WebGL unavailable/)
  await click('Retry 3D');assert.ok(document.querySelector('[data-fallback]'))
  dom.window.WebGL2RenderingContext=class {};dom.window.HTMLCanvasElement.prototype.getContext=()=>({getExtension:()=>null})
  await click('Retry 3D');assert.ok(document.querySelector('[data-canvas]'));assert.ok(!document.querySelector('[role=status]'))
 }
})
uiTest('startup failure remounts only the renderer on retry; repeated failures stay visible',async({mount,click})=>{
 canvasFailure=true
 const error=console.error;console.error=()=>{}
 try{await mount(scene());await click('Retry 3D')}finally{console.error=error}
 assert.match(document.body.textContent,/renderer failed/);assert.ok(document.querySelector('[data-fallback]'))
 canvasFailure=false;await click('Retry 3D');assert.ok(document.querySelector('[data-canvas]'))
})
uiTest('asynchronous renderer construction failures cannot escape as rejected configuration promises',async({mount,click})=>{
 configureRenderer=true;factoryFailure=true
 await mount(scene())
 assert.ok(startupResult instanceof Promise);assert.ok(document.querySelector('[data-fallback]'));assert.match(document.body.textContent,/renderer failed/)
 // No fake renderer is handed to Fiber when construction fails. Its failed
 // setup is abandoned when the Canvas is unmounted in favor of the fallback.
 let settled=false;startupResult.then(()=>{settled=true},()=>{settled=true});await Promise.resolve();assert.equal(settled,false)
 factoryFailure=false;await click('Retry 3D')
 assert.equal((await startupResult).testRenderer,true);assert.ok(factoryOptions.canvas instanceof window.HTMLCanvasElement);assert.ok(document.querySelector('[data-canvas]'))
})
uiTest('context loss, repeated loss and pre-existing lost contexts use the same retry contract',async({mount,click,lose})=>{
 await mount(scene());await lose();assert.match(document.body.textContent,/context lost/)
 await click('Retry 3D');assert.ok(document.querySelector('[data-canvas]'));await lose();assert.ok(document.querySelector('[data-fallback]'))
 gl.getContext=()=>({isContextLost:()=>true});await click('Retry 3D');assert.match(document.body.textContent,/context lost/)
 gl.getContext=()=>({isContextLost:()=>false});await click('Retry 3D');assert.ok(document.querySelector('[data-canvas]'))
})
uiTest('frame exceptions show fallback and suppress subsequent renders until retry',async({mount,click})=>{
 await mount(scene());let renders=0
 const callback=renderFrame,state={gl:{render(){renders++;throw Error('TEST GPU frame')}},scene:{},camera:{}}
 await act(async()=>callback(state));await act(async()=>callback(state));assert.equal(renders,1)
 assert.match(document.body.textContent,/renderer failed/);assert.ok(document.querySelector('[data-fallback]'))
 await click('Retry 3D');let recovered=0;await act(async()=>renderFrame({gl:{render(){recovered++}},scene:{},camera:{}}));assert.equal(recovered,1)
})
uiTest('context listeners are removed on unmount and toggling to 2D',async({dom,mount})=>{
 await mount(scene());await mount(scene({enabled:false}))
 let event=new dom.window.Event('webglcontextlost',{cancelable:true});gl.domElement.dispatchEvent(event);assert.equal(event.defaultPrevented,false)
 await mount(scene());await mount(null)
 event=new dom.window.Event('webglcontextlost',{cancelable:true});gl.domElement.dispatchEvent(event);assert.equal(event.defaultPrevented,false)
})
uiTest('failure and retry messages use the Chinese scene catalog',async({mount,lose,click})=>{
 globalThis.sceneTestLocale='zh-CN';await mount(scene());await lose()
 assert.match(document.body.textContent,/WebGL 上下文丢失/);await click('重试 3D');assert.ok(document.querySelector('[data-canvas]'))
 for(const value of Object.values(sceneMessages)){assert.ok(value.en);assert.ok(value['zh-CN'])}
})

const graph={neurons:[{id:'1',position:[1,2,3],class:'TEST'},{id:'2',class:'TEST'},{id:'3',class:'TEST'}],edges:[{edge:0,pre:'1',post:'2',count:4,baseline_weight:.2,weight:.4,multiplier:2},{edge:1,pre:'2',post:'3',count:1,weight:0}]}
const frames=[0,1,2].map(time=>({time,tick:time*10000,brain:[{sampled_nodes:[{id:'1',activity:time},{id:'2',activity:time===1?8:0}]}]}))
for(const morphology of [false,true])for(const failure of ['missing','context','startup','construction','frame'])uiTest(`${morphology?'morphology':'soma'} fallback preserves selected neuron, connections and recorded trace after ${failure}`,async({dom,mount,click,lose})=>{
 const connectome=(morphology?'b':'a').repeat(64),activity=new Map([['1',0],['2',0]]),before=structuredClone({graph,frames})
 globalThis.fetch=async url=>({ok:!url.includes('morphology')||morphology,json:async()=>url.includes('morphology')?{schema:'connectome-morphology/v1',connectome_sha256:connectome,source:'TEST',coordinate_unit_nm:8,neurons:[{id:'1',positions:[1,2,3,4,5,6],edges:[0,1]}],missing_ids:['2','3']}:{schema:'connectome-anatomy/v1',connectome_sha256:connectome,neuron_count:3,position_count:1,missing_position_count:2,positions:[1,2,3]}})
 if(failure==='missing')dom.window.WebGL2RenderingContext=undefined
 if(failure==='startup')canvasFailure=true
 if(failure==='construction'){configureRenderer=true;factoryFailure=true}
 let sought=null
 const props={connectome,graph,activity,scale:8,frames,slot:0,time:0,onSeek:t=>{sought=t},focusId:'2'}
 const error=console.error;if(failure==='startup')console.error=()=>{}
 try{await mount(React.createElement(AnatomicalBrain,props))}finally{console.error=error}
 const inspector=document.querySelector('.local-brain-neighborhood')
 await act(async()=>{const edge=document.querySelector('[aria-label="Inspect edge"]');edge.value='1';edge.dispatchEvent(new dom.window.Event('change',{bubbles:true}))})
 if(failure==='context')await lose()
 if(failure==='frame')await act(async()=>renderFrame({gl:{render(){throw Error('TEST frame')}},scene:{},camera:{}}))
 assert.equal(document.querySelector('.local-brain-neighborhood'),inspector)
 assert.equal(document.querySelector('[aria-label="Focus neuron"]').value,'2')
 assert.equal(document.querySelector('[aria-label="Inspect edge"]').options.length,2)
 assert.equal(document.querySelector('[aria-label="Inspect edge"]').value,'1')
 assert.equal(document.querySelector('.neuron-activity-trace').dataset.neuronId,'2')
 assert.match(document.body.textContent,/0.00 Hz/);assert.match(document.body.textContent,/layout is schematic, not anatomical coordinates/)
 assert.match(document.body.textContent,/Unavailable; activity can still be inspected below/)
 assert.equal(document.querySelector('[data-neuron="3"]').dataset.recorded,'false')
 await click('Go to recorded peak');assert.equal(sought,1)
 // A controlled selection without samples must remain missing, never filled with 0.
 await mount(React.createElement(AnatomicalBrain,{...props,focusId:'3',time:1}))
 assert.match(document.querySelector('.neuron-activity-trace').textContent,/did not record this neuron/)
 assert.equal(document.querySelector('[data-neuron-trace]'),null)
 await mount(React.createElement(AnatomicalBrain,{...props,time:1,activity:new Map([['1',1],['2',8]])}))
 dom.window.WebGL2RenderingContext=class {};canvasFailure=false;factoryFailure=false;await click('Retry 3D')
 assert.ok(document.querySelector('[data-canvas]'));assert.equal(canvasProps.orthographic===true,morphology)
 assert.equal(document.querySelector('[aria-label="Focus neuron"]').value,'2');assert.match(document.querySelector('.neuron-activity-summary').textContent,/8.00 Hz/)
 assert.deepEqual({graph,frames},before)
})

// jsdom has no layout engine or viewport media evaluation. Apply only the
// width-matched CSS rules to audit shrink/wrap constraints at both requested
// sizes; this does not claim a rasterized browser/screenshot check.
for(const width of [390,1440])uiTest(`scene CSS keeps canvases shrinkable and controls usable at ${width}px`,async({dom,mount})=>{
 await mount(React.createElement('div',{className:'anatomical-brain'},
  React.createElement('div',{className:'anatomical-brain-stage'},scene()),
  React.createElement('div',{className:'morphology-controls'},React.createElement('div',{role:'group'})),
  React.createElement('div',{className:'morphology-playback'})))
 const sheet=document.createElement('style')
 sheet.textContent=['features/arena/anatomicalBrain.css','features/arena/scenePresentation.css','features/phenotype/probeScene.css','shared/sceneAvailability.css'].map(file=>fs.readFileSync(path.join(web,'src',file),'utf8')).join('\n')
 document.head.append(sheet)
 const matches=query=>[...query.matchAll(/(min|max)-width:\s*(\d+)px/g)].every(([,bound,n])=>bound==='max'?width<=Number(n):width>=Number(n))
 const atWidth=rules=>[...rules].flatMap(rule=>rule.type===dom.window.CSSRule.MEDIA_RULE?matches(rule.conditionText)?atWidth(rule.cssRules):[]:rule.cssText).join('\n')
 const css=atWidth(sheet.sheet.cssRules);sheet.textContent=css
 const style=selector=>dom.window.getComputedStyle(document.querySelector(selector))
 assert.equal(style('.anatomical-brain-stage').height,width===390?'300px':'370px')
 for(const selector of ['.anatomical-brain','.anatomical-brain-stage','.scene-availability','.scene-availability-content'])assert.equal(style(selector).minWidth,'0',selector)
 assert.equal(style('.scene-availability').maxWidth,'100%')
 assert.equal(style('.morphology-controls [role=group]').flexWrap,'wrap')
 if(width===390)assert.equal(style('.morphology-playback').flexWrap,'wrap')
 // Failure descriptions and retry controls must fit the same constrained pane.
 await act(async()=>renderFrame({gl:{render(){throw Error('TEST failure')}},scene:{},camera:{}}))
 // Inspect the matching failure rule directly: jsdom does not reliably
 // recompute :has() ancestor styles after descendant attributes change.
 const failureRule=[...sheet.sheet.cssRules].find(rule=>rule.selectorText==='.anatomical-brain-stage:has([data-scene-available=false])')
 assert.ok(document.querySelector(failureRule.selectorText))
 assert.equal(failureRule.style.height,'auto');assert.equal(failureRule.style.getPropertyValue('touch-action'),'auto')
 assert.equal(style('.scene-availability-notice').flexWrap,'wrap')
 assert.equal(style('.scene-availability-notice').overflowWrap,'anywhere')
 if(width===390)assert.equal(style('.scene-availability-notice button').minHeight,'36px')
 const extra=document.createElement('div');extra.innerHTML='<div class="scene-presentation"><div class="scene-presentation-toolbar"></div></div><div class="probe-scene"><div class="probe-scene-viewport"></div><div class="probe-scene-toolbar"></div></div>';document.body.append(extra)
 for(const selector of ['.scene-presentation','.probe-scene','.probe-scene-viewport']){assert.equal(style(selector).minWidth,'0');assert.equal(style(selector).maxWidth,'100%');assert.equal(style(selector).boxSizing,'border-box')}
 for(const selector of ['.scene-presentation-toolbar','.probe-scene-toolbar'])assert.equal(style(selector).flexWrap,'wrap')
 if(width===390)assert.equal(style('.probe-scene-viewport').height,'300px')
})
