import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'

const source=fs.readFileSync(new URL('../src/features/arena/replayComparisonContext.ts',import.meta.url),'utf8')
const output=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText
const module=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'))

const match=request=>({request})
const receipt=(overrides={})=>({request:{mode:'duel',fly_ids:['fly-a','fly-b'],map_id:'orchard',seed:42,duration_seconds:10,bridge_profile:'legacy-v1',sensory_profile:'odor-only-v1'},readout_sha256:'readout-a',runtime:{sources:{'runner.py':'source-a'},lock_sha256:'lock-a',connectome_sha256:'graph-a',replay_policy:{id:'pose-100hz-events-20hz-v1',pose_ticks:100},motor_id:'dn-cpg-approach-v4',sensory_profile:{id:'odor-only-v1'}},replay_policy:{id:'pose-100hz-events-20hz-v1',pose_ticks:100},...overrides})

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

for(const [id,change] of [
 ['horizon',r=>{r.request.duration_seconds=20}],
 ['sensoryProfile',r=>{r.request.sensory_profile='engineered-contact-support-v1'}],
 ['motorProfile',r=>{r.runtime.motor_id='different-motor'}],
 ['recordingPolicy',r=>{r.replay_policy.pose_ticks=50}],
 ['mode',r=>{r.request.mode='contest'}],
 ['participant',r=>{r.request.fly_ids[0]='fly-c'}],
 ['opponents',r=>{r.request.fly_ids[1]='fly-c'}],
])test(`independent ${id} differences remain descriptive`,()=>{
 const right=receipt();change(right)
 const context=module.replayComparisonContext({receipt:receipt()},{receipt:right})
 assert.equal(context.interpretation,'descriptive')
 assert.deepEqual(context.conditions.filter(c=>c.status==='differ').map(c=>c.id),[id])
 assert.equal(context.hasUnavailable,false)
})

for(const missingSide of ['left','right'])test(`asymmetric missing evidence on the ${missingSide} never becomes agreement`,()=>{
 const missing=receipt({request:{...receipt().request,duration_seconds:null,sensory_profile:null,mode:null,fly_ids:null},readout_sha256:null,runtime:{},replay_policy:null})
 const context=module.replayComparisonContext({receipt:missingSide==='left'?missing:receipt()},{receipt:missingSide==='right'?missing:receipt()})
 assert.equal(context.interpretation,'unavailable');assert.equal(context.hasDifferences,false)
 for(const condition of context.conditions){
  if(['map','seed'].includes(condition.id)){assert.equal(condition.status,'agree');continue}
  assert.equal(condition.status,'unavailable',condition.id)
  assert.equal(condition[missingSide],null,condition.id)
  assert.notEqual(condition[missingSide==='left'?'right':'left'],null,condition.id)
 }
})

test('motor profile objects compare their IDs across receipt and runtime representations',()=>{
 for(const key of ['receipt','runtime']){
  const left=receipt(),right=receipt()
  const target=key==='receipt'?right:right.runtime
  target.motor_profile={id:left.runtime.motor_id,description:'Additional manifest metadata'}
  let context=module.replayComparisonContext({receipt:left},{receipt:right})
  assert.equal(context.conditions.find(c=>c.id==='motorProfile').status,'agree')
  target.motor_profile.id='different-motor'
  context=module.replayComparisonContext({receipt:left},{receipt:right})
  assert.equal(context.conditions.find(c=>c.id==='motorProfile').status,'differ')
  target.motor_profile={description:'Missing identity'}
  context=module.replayComparisonContext({receipt:left},{receipt:right})
  assert.equal(context.conditions.find(c=>c.id==='motorProfile').status,'unavailable')
 }
})

test('participant and opponent identities follow the selected recorded individual',()=>{
 const left={receipt:receipt(),participant:{id:'fly-b'}},right={receipt:receipt(),participant:{id:'fly-a'}}
 const context=module.replayComparisonContext(left,right)
 assert.deepEqual(context.conditions.find(c=>c.id==='participant'),{id:'participant',label:'participant identity',status:'differ',left:'fly-b',right:'fly-a'})
 assert.equal(context.conditions.find(c=>c.id==='opponents').left,'["fly-a"]')
 assert.equal(context.conditions.find(c=>c.id==='opponents').right,'["fly-b"]')
 const solo=receipt({request:{...receipt().request,mode:'forage',fly_ids:['fly-a']}})
 assert.equal(module.replayComparisonContext({receipt:solo},{receipt:solo}).conditions.find(c=>c.id==='opponents').left,'[]')
 const unknown=module.replayComparisonContext({receipt:solo,participant:{id:'missing'}},{receipt:solo})
 assert.equal(unknown.conditions.find(c=>c.id==='participant').status,'unavailable')
})

test('receipt mode and identities override stale match metadata',()=>{
 const context=module.replayComparisonContext({match:match({mode:'forage',fly_ids:['stale']}),receipt:receipt()},{receipt:receipt()})
 for(const id of ['mode','participant','opponents'])assert.equal(context.conditions.find(c=>c.id===id).status,'agree')
})
