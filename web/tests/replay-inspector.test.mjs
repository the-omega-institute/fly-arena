import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'

const source=fs.readFileSync(new URL('../src/features/arena/replayInspector.ts',import.meta.url),'utf8')
const output=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText
const module=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'))

test('replay flow has one ordered path and selection follows the recorded subject',()=>{
 const scene={flies:[{id:'left'},{id:'right'}]}
 assert.equal(module.selectedReplaySlot(scene,'right'),1)
 assert.equal(module.selectedReplaySlot(scene,'missing',1),1)
 assert.equal(module.selectedReplaySlot(scene,'missing',9),1)
})

test('outcome preserves missing fields',()=>{
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

test('recorded result tokens have bilingual labels',async()=>{
 const source=fs.readFileSync(new URL('../src/shared/messages/replay.ts',import.meta.url),'utf8')
 const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText
 const {replayMessages}=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'))
 for(const token of ['draw','win','solo']){
  const label=replayMessages[module.replayOutcomeLabel(token)]
  assert.ok(label.en);assert.ok(label['zh-CN']);assert.notEqual(label['zh-CN'],token)
 }
 assert.equal(module.replayOutcomeLabel('future-result'),'future-result')
})
