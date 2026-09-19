import test from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
import fs from 'node:fs'
async function moduleAt(path) {
  const {outputText}=ts.transpileModule(fs.readFileSync(new URL(path,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}})
  return import('data:text/javascript;base64,'+Buffer.from(outputText).toString('base64'))
}
const {reconcileDesignSelection}=await moduleAt('../src/features/phenotype/designSelection.ts')
const {requestReplay}=await moduleAt('../src/features/arena/replayRequest.ts')
const flies=[{id:'A',owner:'owner'},{id:'B',owner:'owner'},{id:'C',owner:'other'}]
test('explicit B and explicit blank survive fresh arrays and reordering under selected A',()=>{
  let choice=reconcileDesignSelection(undefined,flies,'A','owner')
  assert.equal(choice.design,'A')
  choice={...choice,design:'B'}
  for(let i=0;i<3;i++) {
    choice=reconcileDesignSelection(choice,structuredClone(flies).reverse(),'A','owner')
    assert.equal(choice.design,'B')
  }
  choice=reconcileDesignSelection({...choice,design:''},flies,'A','owner')
  assert.equal(choice.design,'')
})
test('selection/context/identity changes initialize, missing or transferred choices clear and do not resurrect',()=>{
  const b={...reconcileDesignSelection(undefined,flies,'A','owner'),design:'B'}
  assert.equal(reconcileDesignSelection(b,flies,'C','other').design,'C')
  assert.equal(reconcileDesignSelection(b,flies,'C','owner').design,'A')
  assert.equal(reconcileDesignSelection(undefined,flies,'A','owner').design,'A')
  assert.equal(reconcileDesignSelection(b,flies,'A',undefined).design,'')
  for(const refreshed of [flies.filter(f=>f.id!=='B'),flies.map(f=>f.id==='B'?{...f,owner:'other'}:f)]) {
    const cleared=reconcileDesignSelection(b,refreshed,'A','owner')
    assert.equal(cleared.design,'')
    assert.equal(reconcileDesignSelection(cleared,flies,'A','owner').design,'')
  }
  assert.equal(reconcileDesignSelection(undefined,[], 'missing','owner').design,'')
})
function transport() {
  const calls=[]
  return {calls,fetch:(path,options)=>new Promise((resolve,reject)=>calls.push({path,options,resolve,reject}))}
}
const scene=id=>({flies:[{id}],size:12})
const frames=id=>[{time:0,scores:[id]},{time:3,scores:[id]}]
const events=id=>[{type:'intake',tick:id}]
test('slow replay clears ready A immediately and commits only the complete B pair',async()=>{
  const net=transport();let state={matchId:'A',status:'ready',scene:scene('A'),frames:frames(1)}
  const request=requestReplay('B',net.fetch,next=>state=next)
  assert.equal(state.matchId,'B');assert.equal(state.status,'loading');assert.equal(state.scene,null);assert.deepEqual(state.frames,[])
  net.calls[0].resolve(scene('B'));await Promise.resolve()
  assert.equal(state.scene,null)
  net.calls[1].resolve(frames(2));net.calls[2].resolve(events(2));await request.done
  assert.equal(state.status,'ready');assert.equal(state.scene.flies[0].id,'B');assert.equal(state.frames[0].scores[0],2)
})
for(const failIndex of [0,1])test(`replay endpoint ${failIndex} failure discards partial data and aborts its sibling`,async()=>{
  const net=transport();let state
  const request=requestReplay('B',net.fetch,next=>state=next)
  net.calls[failIndex].reject(new Error('HTTP 503'))
  await request.done
  assert.equal(state.status,'error');assert.equal(state.matchId,'B');assert.equal(state.error,'HTTP 503');assert.equal(state.scene,null);assert.deepEqual(state.frames,[])
  assert.ok(net.calls.every(c=>c.options.signal.aborted))
  net.calls[1-failIndex].resolve(failIndex?scene('B'):frames(2));net.calls[2].resolve(events(2));await Promise.resolve()
  assert.equal(state.status,'error')
})
test('A → B → C cancellation rejects late success/error even if transport ignores abort',async()=>{
  const net=transport();const commits=[];const commit=s=>commits.push(s)
  const a=requestReplay('A',net.fetch,commit);a.cancel()
  const b=requestReplay('B',net.fetch,commit);b.cancel()
  const c=requestReplay('C',net.fetch,commit)
  assert.ok(net.calls.slice(0,6).every(c=>c.options.signal.aborted))
  assert.ok(net.calls.slice(6).every(c=>!c.options.signal.aborted))
  net.calls[6].resolve(scene('C'));net.calls[7].resolve(frames(3));net.calls[8].resolve(events(3));await c.done
  net.calls[0].resolve(scene('A'));net.calls[1].resolve(frames(1));net.calls[2].resolve(events(1));await a.done
  net.calls[3].reject(new Error('obsolete 503'));net.calls[4].resolve(frames(2));net.calls[5].resolve(events(2));await b.done
  assert.deepEqual(commits.map(s=>[s.matchId,s.status]),[['A','loading'],['B','loading'],['C','loading'],['C','ready']])
})
test('cancel on unmount/queued focus produces no error or ready commit and permits same-ID retry',async()=>{
  const net=transport();const commits=[]
  const first=requestReplay('A',net.fetch,s=>commits.push(s));first.cancel()
  const retry=requestReplay('A',net.fetch,s=>commits.push(s))
  net.calls[3].resolve(scene('A-new'));net.calls[4].resolve(frames(7));net.calls[5].resolve(events(7));await retry.done
  net.calls[0].reject(new Error('old A'));net.calls[1].resolve(frames(1));net.calls[2].resolve(events(1));await first.done
  assert.equal(commits.length,3);assert.equal(commits.at(-1).scene.flies[0].id,'A-new')
})
test('empty frames leave an unavailable replay, never a verified scene',async()=>{
  const net=transport();let state
  const request=requestReplay('A',net.fetch,s=>state=s)
  net.calls[0].resolve(scene('A'));net.calls[1].resolve([]);net.calls[2].resolve([]);await request.done
  assert.equal(state.status,'error');assert.equal(state.scene,null);assert.deepEqual(state.frames,[])
})
