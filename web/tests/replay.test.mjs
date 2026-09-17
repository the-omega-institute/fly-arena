import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'

const {outputText}=ts.transpileModule(fs.readFileSync(new URL('../src/features/arena/replayFrames.ts',import.meta.url),'utf8'),
  {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}})
const {selectReplayFrames}=await import('data:text/javascript;base64,'+Buffer.from(outputText).toString('base64'))
const recorded=times=>times.map((time,i)=>({time,poses:[[i,-i,0,1,0,0,0]],tick:Math.round(time*10000)}))

for(const cadence of [.05,.01]) {
  const frames=recorded(Array.from({length:Math.round(1/cadence)+1},(_,i)=>i*cadence))
  test(`${1/cadence} Hz uses actual timestamps, exact samples, and unmodified geometry`,()=>{
    const before=structuredClone(frames)
    for(let i=0;i<frames.length-1;i++) {
      const exact=selectReplayFrames(frames,frames[i].time)
      assert.equal(exact.frame,frames[i]);assert.equal(exact.next,frames[i+1]);assert.equal(exact.alpha,0)
      const mid=selectReplayFrames(frames,(frames[i].time+frames[i+1].time)/2)
      assert.equal(mid.frame,frames[i]);assert.equal(mid.next,frames[i+1])
      assert.ok(Math.abs(mid.alpha-.5)<1e-12)
      assert.equal(mid.frame.poses,frames[i].poses)
    }
    assert.deepEqual(frames,before)
  })
  test(`${1/cadence} Hz clamps initial/final selection and arbitrary seeking`,()=>{
    for(const t of [1,1.001,10]) {
      const end=selectReplayFrames(frames,t)
      assert.equal(end.frame,frames.at(-1));assert.equal(end.next,end.frame);assert.equal(end.alpha,0)
    }
    const start=selectReplayFrames(frames,-.2)
    assert.equal(start.frame,frames[0]);assert.equal(start.alpha,0)
    for(const t of [.99,.1,.43,0,.8]) {
      const {frame,next,alpha}=selectReplayFrames(frames,t)
      assert.ok(frame.time<=t&&next.time>=t);assert.ok(alpha>=0&&alpha<=1)
    }
  })
}

test('empty, singleton, and partial final intervals remain safe at both cadences',()=>{
  assert.deepEqual(selectReplayFrames([],0),{frame:undefined,next:undefined,alpha:0})
  const one=recorded([0]);assert.equal(selectReplayFrames(one,1).next,one[0])
  for(const times of [[0,.05,.06],[0,.01,.02,.023]]) {
    const frames=recorded(times),t=(times.at(-2)+times.at(-1))/2
    const between=selectReplayFrames(frames,t)
    assert.equal(between.frame,frames.at(-2));assert.equal(between.next,frames.at(-1))
    assert.ok(Math.abs(between.alpha-.5)<1e-12)
    assert.equal(selectReplayFrames(frames,times.at(-1)).frame,frames.at(-1))
  }
})

test('uneven recorded timestamps determine selection, independently of index or nominal Hz',()=>{
  const frames=recorded([0,.01,.03,.037])
  const selection=selectReplayFrames(frames,.02)
  assert.equal(selection.frame,frames[1]);assert.equal(selection.next,frames[2])
  assert.ok(Math.abs(selection.alpha-.5)<1e-12)
})
