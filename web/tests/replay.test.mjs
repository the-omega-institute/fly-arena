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

const eventsModule=ts.transpileModule(fs.readFileSync(new URL('../src/features/arena/lifeEvents.ts',import.meta.url),'utf8'),
  {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}})
const {lifeEvents,lifeEventPage,lifeEventPageAtTime,eventSampleWindow}=await import('data:text/javascript;base64,'+Buffer.from(eventsModule.outputText).toString('base64'))

test('long life records retain early feeding and every subsequent contact across pages',()=>{
  const early={tick:50,type:'intake',slot:0}
  const late=Array.from({length:40},(_,i)=>({tick:100+i*100,type:'environment_contact',slot:0}))
  const shared={tick:75,type:'contact',slots:[0,1]}
  const other={tick:20,type:'intake',slot:1}
  const source=[...late,other,early,shared],original=[...source]
  const all=lifeEvents(source,0)
  assert.equal(all[0],early);assert.equal(all[1],shared)
  assert.equal(all.length,42)
  const collected=[]
  for(let page=0;page<lifeEventPage(all,0).pages;page++)collected.push(...lifeEventPage(all,page).rows)
  assert.deepEqual(collected,all)
  assert.deepEqual(source,original)
  assert.deepEqual(lifeEvents(source,0,'food'),[early])
  assert.equal(lifeEvents(source,0,'contact').length,41)
  assert.deepEqual(lifeEvents(source,1),[other,shared])
  assert.deepEqual(lifeEvents(source,0,'outcome'),[])
  assert.equal(lifeEventPage(all,999).page,3)
  assert.deepEqual(lifeEventPage([],0).rows,[])
})

test('playhead location finds the containing event page at start, middle and end',()=>{
  const events=Array.from({length:37},(_,i)=>({tick:(i+1)*10000,type:'intake',slot:0}))
  assert.equal(lifeEventPageAtTime(events,0),0)
  assert.equal(lifeEventPageAtTime(events,13),1)
  assert.equal(lifeEventPageAtTime(events,100),3)
  assert.equal(lifeEventPageAtTime([],4),0)
  const boundary=[...Array.from({length:12},(_,i)=>({tick:i,type:'intake'})),{tick:300,type:'intake'}]
  assert.equal(lifeEventPageAtTime(boundary,.03),1) // Exact recorded decimal time, without multiplication drift.
})

test('event seeking uses actual post-event samples at 20 Hz, 100 Hz and irregular cadence',()=>{
  for(const times of [[0,.05,.1],[0,.01,.02],[0,.003,.037,.1]]){
    const frames=recorded(times)
    const event={tick:Math.round(times[1]*10000),type:'food_contact'}
    const window=eventSampleWindow(frames,event)
    assert.equal(window.before,frames[1]);assert.equal(window.after,frames[2])
    const initial=eventSampleWindow(frames,{...event,tick:0})
    assert.equal(initial.after,frames[1])
    const final=eventSampleWindow(frames,{...event,tick:Math.round(times.at(-1)*10000)})
    assert.equal(final.before,frames.at(-1));assert.equal(final.after,frames.at(-1))
  }
  assert.equal(eventSampleWindow([],{tick:0,type:'intake'}),null)
})

const chaptersModule=ts.transpileModule(fs.readFileSync(new URL('../src/features/arena/behaviorSummary.ts',import.meta.url),'utf8'),
  {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}})
const {behaviorChapters,thoraxTilt}=await import('data:text/javascript;base64,'+Buffer.from(chaptersModule.outputText).toString('base64'))
const behaviorFrames=(times,positions,scores)=>times.map((time,i)=>({time,tick:Math.round(time*10000),positions:[positions[i]],scores:[scores[i]]}))

test('behavior chapters expose movement without intake and conserve actual path across irregular boundaries',()=>{
  const frames=behaviorFrames([0,2,5.1,7,10.2,11],[[0,0],[3,4],[0,0],[0,3],[0,0],[4,0]],[0,1,1,1,1,1])
  const events=[{tick:51000,type:'food_contact',slot:0},{tick:51000,type:'contact',slots:[0,1]},
    {tick:70000,type:'environment_contact',slot:1},{tick:102000,type:'environment_contact',slot:0}]
  const chapters=behaviorChapters(frames,events,0)
  assert.deepEqual(chapters.map(c=>[c.start,c.end]),[[0,5.1],[5.1,10.2],[10.2,11]])
  assert.deepEqual(chapters.map(c=>c.path),[10,6,4])
  assert.deepEqual(chapters.map(c=>c.displacement),[0,0,4])
  assert.deepEqual(chapters.map(c=>c.intake),[1,0,0])
  assert.deepEqual(chapters.map(c=>c.foodContacts),[1,0,0])
  assert.deepEqual(chapters.map(c=>c.environmentContacts),[0,1,0])
  assert.deepEqual(chapters.map(c=>c.flyContacts),[1,0,0])
  assert.equal(behaviorChapters(frames,[{tick:51000,type:'contact',slots:[1,2]}],0)[0].flyContacts,0)
})

test('missing body or score records never become zero movement or zero intake',()=>{
  const frames=behaviorFrames([0,2,5],[[0,0],null,[1,0]],[0,undefined,undefined])
  const chapter=behaviorChapters(frames,[],0)[0]
  assert.equal(chapter.path,null)
  assert.equal(chapter.displacement,1)
  assert.equal(chapter.intake,null)
  assert.deepEqual(behaviorChapters([],[],0),[])
  assert.deepEqual(behaviorChapters(frames.slice(0,1),[],0),[])
})

test('short contact sample has one chapter; initial and final events are retained',()=>{
  const frames=behaviorFrames([0,.37,1],[[0,0],[2,0],[6,0]],[0,0,1.0552])
  const events=[{tick:0,type:'food_contact',slot:0},{tick:10000,type:'exit',slot:0}]
  const [chapter]=behaviorChapters(frames,events,0)
  assert.equal(chapter.end,1);assert.equal(chapter.intake,1.0552)
  assert.equal(chapter.foodContacts,1);assert.equal(chapter.exits,1)
})


test('response windows expose delayed neural activity using actual timestamps',()=>{
  const frames=recorded([0,.03,.05,.13,.17,.5,.55])
  const event={tick:300,type:'food_contact',slot:0}
  assert.equal(eventSampleWindow(frames,event).after.time,.05)
  assert.equal(eventSampleWindow(frames,event,100).after.time,.13)
  assert.equal(eventSampleWindow(frames,event,500).after.time,.55)
  assert.equal(eventSampleWindow(frames,event,250).after.time,.5)
  assert.equal(eventSampleWindow(frames,event,1000).after.time,.55)
  assert.equal(eventSampleWindow(frames,event,100).before.time,.03)
  assert.equal(eventSampleWindow(frames,{...event,tick:5500},100).after.time,.55)
})

test('thorax posture distinguishes yaw from inversion and cancels fixed mesh rotation',()=>{
  const scene={body:{geoms:[{slot:0,name:'fly-0/c_thorax'}]}}
  const pose=q=>({poses:[[0,0,0,...q]]})
  const a=Math.SQRT1_2,initial=pose([a,0,a,0]) // Mesh has a fixed 90-degree Y rotation.
  assert.ok(thoraxTilt(scene,initial,initial,0)<1e-5)
  assert.ok(thoraxTilt(scene,initial,pose([.5,-.5,.5,.5]),0)<1e-5) // Body yaw only.
  assert.ok(Math.abs(thoraxTilt(scene,initial,pose([0,a,0,a]),0)-180)<1e-5) // Body roll 180.
  assert.equal(thoraxTilt(scene,initial,pose([0,0,0,0]),0),null)
  assert.equal(thoraxTilt(scene,initial,undefined,0),null)
  assert.equal(thoraxTilt({body:{geoms:[]}},initial,initial,0),null)
})

const responseModule=ts.transpileModule(fs.readFileSync(new URL('../src/features/arena/responseSignals.ts',import.meta.url),'utf8'),
 {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}})
const {responseSignals,responsePath,responsePointAt}=await import('data:text/javascript;base64,'+Buffer.from(responseModule.outputText).toString('base64'))
test('response signals preserve input/block timing, gaps and measured irregular body speed',()=>{
 const frames=[
  {time:0,positions:[[0,0,0]],senses:[{taste:0,contact_activity:{taste:0}}]},
  {time:.01,positions:[[.03,.04,0]],senses:[{taste:1,contact_activity:{taste:null}}]},
  {time:.03,positions:[[.03,.14,0]],senses:[{taste:0,contact_activity:{taste:12}}]},
 ]
 const rows=responseSignals(frames,0,.01)
 assert.deepEqual(rows[0].signals[0].points.map(p=>p.time),[0,0,.019999999999999997])
 assert.deepEqual(rows[1].signals[0].points,[{time:0,value:0},{time:.01,value:null},{time:.03,value:12}])
 assert.equal(responsePointAt(rows[0].signals[0].points,0).value,1)
 assert.equal(responsePointAt(rows[1].signals[0].points,.02).value,null)
 const speed=rows.find(r=>r.id==='speed').signals[0].points
 assert.equal(speed[0].value,null);assert.ok(Math.abs(speed[1].value-5)<1e-10);assert.ok(Math.abs(speed[2].value-5)<1e-10)
 const path=responsePath(rows[1].signals[0].points,0,.03,12)
 assert.equal((path.match(/M/g)||[]).length,2);assert.ok(!path.includes('L'))
 assert.deepEqual(responseSignals(frames,1,.01).flatMap(r=>r.signals).flatMap(s=>s.points).filter(p=>p.value!==null),[])
 assert.equal(responsePath([{time:0,value:NaN}],0,1,1).trim(),'')
 assert.ok(responsePath(rows[0].signals[0].points,0,.03,1,true).includes('H'))
})

const resourceModule=ts.transpileModule(fs.readFileSync(new URL('../src/features/arena/resourceAccounting.ts',import.meta.url),'utf8'),
 {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}})
const {resourceTotal,resourceMoments,resourcePath}=await import('data:text/javascript;base64,'+Buffer.from(resourceModule.outputText).toString('base64'))
test('shared resource transitions use actual observations and preserve zero versus missing',()=>{
 const scene={flies:[{id:'a'},{id:'b'}],food:[{id:'food-0',initial:2}]}
 const frames=[{time:0,food:[2],scores:[0,0]},{time:.03,food:[1.75],scores:[.25,0]},{time:.11,food:[0],scores:[1.5,.5]},{time:.2,food:[0],scores:[1.5,.5]}]
 assert.deepEqual(resourceMoments(scene,frames),{depletions:[{food:0,time:.11}],firstIntake:[.03,.11]})
 assert.equal(resourceTotal([0,0],2),0)
 assert.equal(resourceTotal([1],2),null)
 assert.equal(resourceTotal([0,undefined],2),null)
 assert.equal(resourceTotal([NaN,0],2),null)
 assert.equal(resourceTotal([-1,1],2),null)
 assert.deepEqual(resourceMoments(scene,[frames[0],{time:.05},frames[2]]),{depletions:[],firstIntake:[null,null]})
 const path=resourcePath([frames[0],{time:.05},frames[2]],f=>resourceTotal(f.food,1),2)
 assert.equal((path.match(/M/g)||[]).length,2);assert.ok(!path.includes('L'))
 assert.equal(resourcePath(frames,f=>resourceTotal(f.food,1),0),'')
})

const feedingModule=ts.transpileModule(fs.readFileSync(new URL('../src/features/arena/feedingEpisodes.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}})
const {feedingEpisodes}=await import('data:text/javascript;base64,'+Buffer.from(feedingModule.outputText).toString('base64'))
test('feeding episodes preserve food/participant accounting and split after a missed positive batch',()=>{
 const events=[{type:'intake',tick:9500,slot:0,food:0,amount:.1},{type:'intake',tick:10000,slot:0,food:0,amount:.4},{type:'intake',tick:10000,slot:1,food:0,amount:9},{type:'intake',tick:10000,slot:0,food:1,amount:.2},{type:'intake',tick:11000,slot:0,food:0,amount:.3},{type:'food_contact',tick:9400,slot:0,food:['patch-a']}]
 const {episodes,invalid}=feedingEpisodes(events.reverse(),0,['patch-a','patch-b'],.0001,500)
 assert.equal(invalid,0);assert.deepEqual(episodes.map(e=>[e.foodId,e.firstTick,e.lastTick,e.amount,e.batches]),[['patch-a',9500,10000,.5,2],['patch-b',10000,10000,.2,1],['patch-a',11000,11000,.3,1]])
 assert.deepEqual(episodes[0].contactTimes,[.9400000000000001]);assert.deepEqual(episodes[1].contactTimes,[])
 assert.equal(episodes.reduce((sum,e)=>sum+e.amount,0),1)
})
test('brief physical intake without a contact sample remains a valid distinct record',()=>{
 const result=feedingEpisodes([{type:'intake',tick:35500,slot:0,food:3,amount:.056}],0,['a','b','c','d'],.0001,500)
 assert.equal(result.episodes.length,1);assert.equal(result.episodes[0].amount,.056);assert.deepEqual(result.episodes[0].contactTimes,[])
 assert.equal(result.episodes[0].start,result.episodes[0].end)
})
test('feeding history requires recorded timing and rejects incomplete resource amounts',()=>{
 const events=[{type:'intake',tick:50,slot:0,food:0},{type:'intake',tick:100,slot:0,food:2,amount:1},{type:'intake',tick:200,slot:0,food:0,amount:NaN}]
 assert.deepEqual(feedingEpisodes(events,0,['a'],.0001,500),{episodes:[],invalid:3,timingAvailable:true})
 assert.equal(feedingEpisodes(events,0,['a'],NaN,500).timingAvailable,false)
 assert.equal(feedingEpisodes(events,0,['a'],.0001,0).timingAvailable,false)
})


const cameraModule=ts.transpileModule(fs.readFileSync(new URL('../src/features/arena/followCamera.ts',import.meta.url),'utf8'),
 {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}})
const {recordedCameraTarget,replayLabelOpacity}=await import('data:text/javascript;base64,'+Buffer.from(cameraModule.outputText).toString('base64'))
test('camera seeks the same recorded participant position and rejects missing coordinates',()=>{
 const frame={positions:[[1,2,3],[4,5,6]]},next={positions:[[3,4,5],[6,7,8]]}
 assert.deepEqual(recordedCameraTarget(frame,next,.5,1),[5,6,7])
 assert.deepEqual(recordedCameraTarget(frame,next,4,0),[3,4,5])
 assert.deepEqual(recordedCameraTarget(frame,next,-1,0),[1,2,3])
 assert.deepEqual(recordedCameraTarget(frame,undefined,.5,0),[1,2,3])
 assert.deepEqual(recordedCameraTarget(frame,{positions:[[NaN,2,3]]},.5,0),[1,2,3])
 assert.equal(recordedCameraTarget(frame,next,.5,2),null)
 assert.equal(recordedCameraTarget({positions:[[1,2]]},next,.5,0),null)
 assert.equal(recordedCameraTarget(undefined,next,.5,0),null)
})

test('replay annotations fade near the body and throughout follow mode',()=>{
 assert.ok(replayLabelOpacity(8,false)<replayLabelOpacity(24,false))
 assert.ok(replayLabelOpacity(24,false)<replayLabelOpacity(60,false))
 for(const distance of [0,8,24,60,1000]){
  assert.ok(replayLabelOpacity(distance,true)<=.18)
  assert.ok(replayLabelOpacity(distance,true)<=replayLabelOpacity(distance,false))
 }
})
