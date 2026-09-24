import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import ts from 'typescript'

const source=fs.readFileSync(new URL('../src/features/arena/replayInspector.ts',import.meta.url),'utf8')
const output=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText
const module=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'))

test('replay flow has one ordered path and selection follows the recorded subject',()=>{
 assert.deepEqual(module.replayInspectionSteps,['individual','outcome','navigator','detail','disclosures'])
 const scene={flies:[{id:'left'},{id:'right'}]}
 assert.equal(module.selectedReplaySlot(scene,'right'),1)
 assert.equal(module.selectedReplaySlot(scene,'missing',1),1)
 assert.equal(module.selectedReplaySlot(scene,'missing',9),1)
})

test('navigator keeps only the selected participant, sorts receipts, and removes exact duplicates',()=>{
 const events=[
  {type:'intake',tick:30,slot:0,amount:.2},
  {type:'food_contact',tick:10,slot:1},
  {type:'food_contact',tick:20,slot:0,objects:['food-0']},
  {type:'food_contact',tick:20,slot:0,objects:['food-0']},
  {type:'contact',tick:25,slots:[0,1]},
 ]
 assert.deepEqual(module.replayNavigatorEvents(events,0).map(event=>[event.type,event.tick]),[['food_contact',20],['contact',25],['intake',30]])
})

test('shared playhead chooses a recorded sample and preserves missing outcome fields',()=>{
 const frames=[{time:.1,tick:1000},{time:.2,tick:2000},{time:.8,tick:8000}]
 assert.deepEqual(module.sharedPlayheadSample(frames,{type:'food_contact',tick:1500},0),{index:1,time:.2,eventTime:.15})
 assert.deepEqual(module.sharedPlayheadSample(frames,{type:'food_contact',tick:1500},700),{index:2,time:.8,eventTime:.15})
 assert.equal(module.sharedPlayheadSample([],{type:'food_contact',tick:1}),null)
 const outcome=module.recordedOutcome([{time:0,scores:[0]},{time:1,scores:[]}],0)
 assert.deepEqual(outcome,{score:null,energy:null,duration:1,status:'recorded'})
})

test('world labels hide under measured HUD cards and reappear in clear canvas space',()=>{
 const canvas={left:0,right:600,top:0,bottom:500},hud={left:12,right:280,top:10,bottom:155}
 assert.equal(module.replayLabelHidden({left:180,right:260,top:80,bottom:110},canvas,hud),true)
 assert.equal(module.replayLabelHidden({left:282,right:360,top:80,bottom:110},canvas,hud),true)
 assert.equal(module.replayLabelHidden({left:300,right:440,top:80,bottom:110},canvas,hud),false)
 assert.equal(module.replayLabelHidden({left:100,right:240,top:180,bottom:210},canvas,hud),false)
 assert.equal(module.replayLabelHidden({left:520,right:650,top:180,bottom:210},canvas,hud),true)
 assert.equal(module.replayLabelHidden({left:10,right:140,top:-20,bottom:10},canvas),true)
 assert.equal(module.replayLabelHidden({left:10,right:140,top:20,bottom:50},canvas),false)
})
