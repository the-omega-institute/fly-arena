import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {execFileSync} from 'node:child_process'
import {createRequire} from 'node:module'
import ts from 'typescript'
import * as THREE from 'three'
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {JSDOM} from 'jsdom'

const web=new URL('../',import.meta.url).pathname,out=fs.mkdtempSync(path.join(os.tmpdir(),'arena-geometry-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web,'node_modules')),path.join(out,'node_modules'))
for(const name of ['obstacleGeometry','followCamera','ReplayCamera']){
 const source=fs.readFileSync(path.join(web,`src/features/arena/${name}.${name==='ReplayCamera'?'tsx':'ts'}`),'utf8')
 fs.writeFileSync(path.join(out,name+'.js'),ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText)
}
const require=createRequire(path.join(out,'package.json'))
const {obstacleGeometry,obstacleMatrix,obstacleBatches,arenaBounds}=require('./obstacleGeometry.js')
const {sceneFraming,sceneGrid}=require('./followCamera.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))

// Read the actual map declarations without importing NumPy, starting a simulation,
// or depending on hand-copied geometry fixtures. Only stdlib copy/math are needed.
const maps=JSON.parse(execFileSync('python3',['-c',`
import ast, copy, json, math, sys
module=ast.parse(open(sys.argv[1]).read())
nodes=[]
for node in module.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'MAPS' for t in node.targets): nodes.append(node)
    if isinstance(node, ast.FunctionDef) and node.name == '_walls': nodes.append(node)
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == 'MAPS': nodes.append(node)
scope={'copy':copy,'math':math}
exec(compile(ast.Module(body=nodes, type_ignores=[]),sys.argv[1],'exec'),scope)
print(json.dumps(scope['MAPS']))
`,path.join(web,'../src/flyarena/scenarios.py')],{encoding:'utf8'}))
const sceneFor=map=>({...map,food:map.food.map((p,i)=>({position:[...p,map.food_heights?.[i]??.15]}))})
const close=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-9,`${actual} != ${expected}`)

test('all eleven configured maps preserve every obstacle and recorded transform without mutation',()=>{
 assert.equal(Object.keys(maps).length,11)
 for(const map of Object.values(maps)){
  const before=structuredClone(map),batches=obstacleBatches(map.obstacles,'#123456')
  assert.equal(batches.reduce((sum,batch)=>sum+batch.items.length,0),map.obstacles.length,map.id)
  for(const obstacle of map.obstacles){
   const geometry=obstacleGeometry(obstacle),matrix=obstacleMatrix(geometry)
   assert.deepEqual(geometry.position,obstacle.position);assert.deepEqual(geometry.size,obstacle.size)
   assert.equal(geometry.shape,obstacle.shape||'box')
   const center=new THREE.Vector3().applyMatrix4(matrix)
   center.toArray().forEach((value,axis)=>close(value,obstacle.position[axis]))
   for(let axis=0;axis<3;axis++)close(new THREE.Vector3().setFromMatrixColumn(matrix,axis).length(),obstacle.size[axis])
   const q=obstacle.quaternion||[1,0,0,0],rotation=new THREE.Quaternion(q[1],q[2],q[3],q[0]).normalize()
   const local=new THREE.Vector3(.5,-.5,.5)
   const expected=local.clone().multiply(new THREE.Vector3(...obstacle.size)).applyQuaternion(rotation).add(center)
   close(local.applyMatrix4(matrix).distanceTo(expected),0)
   assert.ok(batches.some(b=>b.items.some(item=>item.color===(obstacle.color||'#123456')&&item.geometry.position.every((v,i)=>v===obstacle.position[i]))))
  }
  assert.deepEqual(map,before)
 }
})

test('rotated non-habitat box and ellipsoid use the same unit geometry transform',()=>{
 const q=[Math.SQRT1_2,0,0,Math.SQRT1_2]
 const box=obstacleGeometry({position:[3,4,5],size:[2,6,4],quaternion:q})
 const sphere=obstacleGeometry({...box,shape:'ellipsoid',quaternion:q})
 const edge=new THREE.Vector3(.5,0,0).applyMatrix4(obstacleMatrix(box))
 close(edge.x,3);close(edge.y,5);close(edge.z,5)
 const ellipsoid=new THREE.SphereGeometry(.5,32,20).applyMatrix4(obstacleMatrix(sphere))
 ellipsoid.computeBoundingBox()
 const size=ellipsoid.boundingBox.getSize(new THREE.Vector3())
 for(const [i,value] of [6,2,4].entries())assert.ok(Math.abs(size.getComponent(i)-value)<1e-5)
 ellipsoid.dispose()
 assert.throws(()=>obstacleGeometry({position:[0,0,0],size:[1,1,1],quaternion:[0,0,0,0]}),/Invalid arena obstacle geometry/)
})

test('leaf ramps rise toward their bridge and enclosure walls retain tangent headings',()=>{
 const ramps=maps.terrarium.obstacles.slice(1,3)
 const inner=ramps.map((o,i)=>new THREE.Vector3(i?-.5:.5,0,.5).applyMatrix4(obstacleMatrix(obstacleGeometry(o))))
 inner.forEach(p=>assert.ok(p.z>.79&&p.z<.81))
 for(const [i,wall] of maps.enclosure.obstacles.slice(0,16).entries()){
  const direction=new THREE.Vector3(1,0,0).applyQuaternion(new THREE.Quaternion(...obstacleGeometry(wall).quaternion))
  close(direction.dot(new THREE.Vector3(Math.cos(i*Math.PI/8),Math.sin(i*Math.PI/8),0)),0)
 }
})

test('enclosure and labyrinth batch wall segments without losing individual colors',()=>{
 const enclosure=obstacleBatches(maps.enclosure.obstacles,'#fff'),labyrinth=obstacleBatches(maps.labyrinth.obstacles,'#fff')
 assert.equal(enclosure.find(b=>b.shape==='box'&&b.material==='rock').items.length,16)
 assert.equal(labyrinth.length,1);assert.equal(labyrinth[0].items.length,8)
 assert.equal(new Set(labyrinth[0].items.map(item=>item.color)).size,2)
})

for(const map of Object.values(maps))test(`${map.id}: overview fits ground and obstacle bounds in portrait and wide viewports`,()=>{
 const bounds=arenaBounds(sceneFor(map))
 for(const aspect of [.45,1,2.4]){
  const framing=sceneFraming(bounds,aspect,40,!!map.task),camera=new THREE.PerspectiveCamera(40,aspect,.05,framing.distance*4+framing.span*4)
  camera.up.set(0,0,1);camera.position.set(...framing.position);camera.lookAt(new THREE.Vector3(...framing.target));camera.updateMatrixWorld()
  for(const x of [bounds.min[0],bounds.max[0]])for(const y of [bounds.min[1],bounds.max[1]])for(const z of [bounds.min[2],bounds.max[2]]){
   const p=new THREE.Vector3(x,y,z).project(camera)
   assert.ok(Math.abs(p.x)<=1/1.14+1e-9&&Math.abs(p.y)<=1/1.14+1e-9,`${map.id} aspect ${aspect}: ${p.toArray()}`)
   assert.ok(p.z>-1&&p.z<1)
  }
 }
})

test('bounds include rotated terrain and raised ellipsoids beyond nominal floor',()=>{
 const angle=Math.PI/4,q=[Math.cos(angle/2),0,0,Math.sin(angle/2)]
 const bounds=arenaBounds({size:2,food:[],obstacles:[{position:[10,0,4],size:[8,2,2],quaternion:q},{position:[-10,0,5],size:[8,2,2],quaternion:q,shape:'ellipsoid'}]})
 close(bounds.max[0],10+5/Math.sqrt(2));close(bounds.min[0],-10-Math.sqrt(8.5));close(bounds.max[2],6)
})

test('camera and grid scale with map size while grid density stays bounded',()=>{
 const small=sceneFraming(arenaBounds(sceneFor(maps.ring)),1.6),large=sceneFraming(arenaBounds(sceneFor(maps.labyrinth)),1.6)
 assert.ok(large.distance>small.distance)
 for(const size of [10,18,24,28,32,80,320,1000]){
  const grid=sceneGrid(size)
  assert.ok(size/grid.cell<=50);assert.equal(grid.section,grid.cell*5);assert.ok(grid.fade>=size)
 }
})

test('camera refits changed map/viewport bounds, preserves manual orbit, and restores the latest overview after following',async()=>{
 const dom=new JSDOM('<main id="root"></main>'),keys=['window','document','IS_REACT_ACT_ENVIRONMENT']
 const originals=Object.fromEntries(keys.map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]))
 Object.defineProperty(globalThis,'window',{configurable:true,value:dom.window});Object.defineProperty(globalThis,'document',{configurable:true,value:dom.window.document});Object.defineProperty(globalThis,'IS_REACT_ACT_ENVIRONMENT',{configurable:true,value:true})
 const root=createRoot(document.getElementById('root')),camera=new THREE.PerspectiveCamera()
 const controls={target:new THREE.Vector3(),update(){camera.lookAt(this.target)}}
 const fiberFile=require.resolve('@react-three/fiber'),fiber=require(fiberFile),originalFiber=require.cache[fiberFile]
 let tick
 require.cache[fiberFile]={id:fiberFile,filename:fiberFile,loaded:true,exports:{...fiber,useThree:()=>({camera}),useFrame:fn=>{tick=fn}}}
 const {ReplayCamera}=require('./ReplayCamera.js')
 const mount=async props=>{await act(async()=>root.render(React.createElement(ReplayCamera,props)));tick({controls})}
 const props={alpha:0,follow:false,overview:[20,-30,40],overviewTarget:[0,0,2]}
 try{
  await mount(props);assert.deepEqual(camera.position.toArray(),props.overview);assert.deepEqual(controls.target.toArray(),props.overviewTarget)
  camera.position.set(22,-29,38);controls.target.set(1,2,3)
  await mount({...props,overview:[...props.overview],overviewTarget:[...props.overviewTarget]})
  assert.deepEqual(camera.position.toArray(),[22,-29,38]);assert.deepEqual(controls.target.toArray(),[1,2,3])
  const resized={...props,overview:[40,-60,80],overviewTarget:[1,0,3]}
  await mount(resized);assert.deepEqual(camera.position.toArray(),resized.overview);assert.deepEqual(controls.target.toArray(),resized.overviewTarget)
  const following={...resized,follow:true,selectedId:'test',scene:{flies:[{id:'test'}]},frame:{positions:[[2,3,1]]}}
  await mount(following);assert.deepEqual(camera.position.toArray(),[7,-4,5])
  await mount({...following,overview:[60,-80,90],overviewTarget:[2,0,4]});assert.deepEqual(camera.position.toArray(),[7,-4,5])
  await mount({...resized,overview:[60,-80,90],overviewTarget:[2,0,4]});assert.deepEqual(camera.position.toArray(),[60,-80,90]);assert.deepEqual(controls.target.toArray(),[2,0,4])
 }finally{
  await act(async()=>root.unmount());require.cache[fiberFile]=originalFiber;dom.window.close()
  for(const key of keys){if(originals[key])Object.defineProperty(globalThis,key,originals[key]);else delete globalThis[key]}
 }
})
