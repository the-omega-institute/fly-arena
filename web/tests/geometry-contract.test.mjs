import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import ts from 'typescript'

const web=new URL('../',import.meta.url).pathname
const fixture=JSON.parse(fs.readFileSync(new URL('../../tests/fixtures/geometry_contract.json',import.meta.url)))
const out=fs.mkdtempSync(path.join(os.tmpdir(),'geometry-contract-'))
fs.writeFileSync(path.join(out,'package.json'),' {"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web,'node_modules')),path.join(out,'node_modules'))
const transpile=(source,jsx=false)=>ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:jsx?ts.JsxEmit.ReactJSX:undefined,esModuleInterop:true}}).outputText
fs.mkdirSync(path.join(out,'src/features/arena'),{recursive:true});fs.mkdirSync(path.join(out,'src/features/phenotype'),{recursive:true})
for(const [relative,target] of [['src/features/arena/obstacleGeometry.ts','src/features/arena/obstacleGeometry.js'],['src/features/phenotype/probeScene.ts','src/features/phenotype/probeScene.js']])fs.writeFileSync(path.join(out,target),transpile(fs.readFileSync(path.join(web,relative),'utf8')))
const {validateObstacleGeometry}=await import(path.join(out,'src/features/arena/obstacleGeometry.js'))
const {probeGeometry}=await import(path.join(out,'src/features/phenotype/probeScene.js'))
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))

test('Python generated fixture uses the same contract id and obstacle vocabulary',()=>{
 assert.equal(fixture.contract.id,'arena-geometry-v1');assert.equal(fixture.contract.units,'mm');assert.equal(fixture.contract.quaternion_order,'wxyz')
 assert.deepEqual(fixture.contract.shapes,['box','ellipsoid'])
 for(const map of Object.values(fixture.maps))for(const scene of Object.values(map))for(const obstacle of scene.obstacles)assert.equal(validateObstacleGeometry(obstacle),true)
})

test('probe adapter accepts every Python generated probe scene without defaults',()=>{
 for(const probes of Object.values(fixture.probes))for(const scene of Object.values(probes)){
  const geometry=probeGeometry(scene);assert.ok(geometry)
  assert.deepEqual(geometry,{size:scene.size,spawns:scene.spawns,obstacles:scene.obstacles,food:scene.food})
 }
})
