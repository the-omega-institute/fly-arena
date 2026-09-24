import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createRequire} from 'node:module'
import ts from 'typescript'

const web=new URL('../',import.meta.url).pathname
const out=fs.mkdtempSync(path.join(os.tmpdir(),'arena-lineage-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
const source=fs.readFileSync(path.join(web,'src/features/life/lineage.ts'),'utf8')
fs.writeFileSync(path.join(out,'lineage.js'),ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText)
const {lineageLayout}=createRequire(path.join(out,'package.json'))('./lineage.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))

test('lineage layout is deterministic, readable by columns, and links only known nodes',()=>{
 const nodes=[{id:'root',label:'Root',depth:-2,relation:'ancestor'},{id:'parent',label:'Parent',depth:-1,relation:'ancestor'},{id:'center',label:'Center',depth:0,relation:'center'},{id:'sibling',label:'Sibling',depth:0,relation:'sibling'},{id:'child',label:'Child',depth:1,relation:'descendant'},{id:'more',label:'More lineage…',depth:2,relation:'descendant',marker:true}]
 const edges=[{from:'root',to:'parent',relation:'parent'},{from:'parent',to:'center',relation:'parent'},{from:'parent',to:'sibling',relation:'sibling'},{from:'center',to:'child',relation:'child'},{from:'child',to:'more',relation:'descendant'},{from:'missing',to:'center',relation:'child'}]
 const first=lineageLayout(nodes,edges,'center'),second=lineageLayout(nodes,edges,'center')
 assert.deepEqual(first,second)
 assert.equal(first.points.find(point=>point.node.id==='center').x,first.points.find(point=>point.node.id==='sibling').x)
 assert.ok(first.points.find(point=>point.node.id==='child').x>first.points.find(point=>point.node.id==='center').x)
 assert.equal(first.paths.length,5)
 assert.ok(first.paths.every(path=>path.path.startsWith('M ')))
})

test('layout keeps keyboard-facing marker nodes in the same geometry contract',()=>{
 const result=lineageLayout([{id:'center',label:'Center',depth:0,relation:'center'},{id:'marker',label:'More lineage…',depth:1,relation:'descendant',marker:true}], [{from:'center',to:'marker',relation:'descendant'}], 'center',160,80)
 const marker=result.points.find(point=>point.node.marker)
 assert.equal(marker.width,160)
 assert.ok(marker.y>0)
 assert.ok(result.width>160&&result.height>=110)
})
