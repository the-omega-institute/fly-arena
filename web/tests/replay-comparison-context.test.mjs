import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'

const source=fs.readFileSync(new URL('../src/features/arena/replayComparisonContext.ts',import.meta.url),'utf8')
const output=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText
const module=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'))

const match=request=>({request})
const receipt=(overrides={})=>({request:{map_id:'orchard',seed:42,duration_seconds:10,bridge_profile:'legacy-v1',sensory_profile:'odor-only-v1'},readout_sha256:'readout-a',runtime:{sources:{'runner.py':'source-a'},lock_sha256:'lock-a',connectome_sha256:'graph-a',replay_policy:{id:'pose-100hz-events-20hz-v1',pose_ticks:100},motor_id:'dn-cpg-approach-v4',sensory_profile:{id:'odor-only-v1'}},replay_policy:{id:'pose-100hz-events-20hz-v1',pose_ticks:100},...overrides})

test('two complete receipts agree across all comparison conditions',()=>{
 const context=module.replayComparisonContext({match:match(receipt().request),receipt:receipt()},{match:match(receipt().request),receipt:receipt()})
 assert.equal(context.interpretation,'matched')
 assert.ok(context.conditions.every(condition=>condition.status==='agree'))
 assert.equal(context.hasDifferences,false)
})

test('different receipt conditions are descriptive only',()=>{
 const left=receipt(),right=receipt({request:{...receipt().request,map_id:'maze',seed:43},readout_sha256:'readout-b',runtime:{...receipt().runtime,sources:{'runner.py':'source-b'}}})
 const context=module.compareReplayConditions({receipt:left},{receipt:right})
 assert.equal(context.interpretation,'descriptive')
 assert.deepEqual(context.conditions.filter(c=>c.status==='differ').map(c=>c.id),['map','seed','bridgeReadout','runtimeSource'])
})

test('missing receipt identities remain unavailable and never become agreement',()=>{
 const context=module.replayComparisonContext({receipt:{request:{map_id:'orchard',seed:42,duration_seconds:10}}},{receipt:{request:{map_id:'orchard',seed:42,duration_seconds:10}}})
 assert.equal(context.interpretation,'unavailable')
 assert.equal(context.conditions.find(c=>c.id==='map').status,'agree')
 assert.equal(context.conditions.find(c=>c.id==='bridgeReadout').status,'unavailable')
 assert.equal(context.conditions.find(c=>c.id==='recordingPolicy').status,'unavailable')
})

test('receipt request values take precedence over stale match metadata',()=>{
 const context=module.replayComparisonContext({match:match({map_id:'wrong',seed:1,duration_seconds:1}),receipt:receipt()},{match:match(receipt().request),receipt:receipt()})
 assert.equal(context.conditions.find(c=>c.id==='map').status,'agree')
 assert.equal(context.conditions.find(c=>c.id==='seed').status,'agree')
 assert.equal(context.conditions.find(c=>c.id==='horizon').status,'agree')
})
