import type {Frame,ReplayEvent} from '../../types'

export const eventLabels:Record<string,[string,string]>={intake:['实际摄入','Food intake'],food_contact:['接触食物','Food contact'],contact:['接触对手','Fly contact'],environment_contact:['接触环境','Environment contact'],odor_detected:['检测到气味','Odor detected'],visual_target_detected:['检测到视觉目标','Visual target detected'],exit:['越过边界','Boundary exit']}
export function recordedRates(frame:Frame|undefined,slot:number){
 const brain=frame?.brain?.[slot]
 return new Map((brain?.sampled_nodes??brain?.top_nodes??[]).filter(n=>Number.isFinite(n.activity)).map(n=>[n.id,n.activity]))
}
export function brainMoments(events:ReplayEvent[],slot:number){
 const last=new Map<string,number>()
 // Present episode onsets, retaining all original events in the existing ledger.
 return events.filter(e=>e.slot!==undefined?e.slot===slot:!e.slots||e.slots.includes(slot)).slice().sort((a,b)=>a.tick-b.tick).filter(e=>{
  const key=e.type+':'+JSON.stringify(e.food??e.objects??e.slots??null),previous=last.get(key);last.set(key,e.tick)
  return e.type!=='intake'||previous===undefined||e.tick-previous>3500
 })
}
export function preEventBaseline(frames:Frame[],event:ReplayEvent|null,slot:number){
 if(!event)return null
 const samples=frames.filter(f=>f.tick<event.tick&&f.tick>=event.tick-1000)
 if(!samples.length)return null
 const maps=samples.map(f=>recordedRates(f,slot)),rates=new Map<string,number>()
 for(const [id] of maps[0])if(maps.every(m=>m.has(id)))rates.set(id,maps.reduce((sum,m)=>sum+m.get(id)!,0)/maps.length)
 return {rates,start:samples[0].time,end:samples.at(-1)!.time,count:samples.length}
}
export function rateChanges(current:Map<string,number>,baseline:Map<string,number>|undefined){
 return [...current].flatMap(([id,value])=>baseline?.has(id)?[{id,current:value,before:baseline.get(id)!,delta:value-baseline.get(id)!}]:[]).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta)||a.id.localeCompare(b.id))
}
export function responseScale(frames:Frame[],event:ReplayEvent|null,slot:number,baseline:Map<string,number>|undefined){
 if(!event||!baseline)return 50
 const magnitudes=frames.filter(f=>f.tick>=event.tick&&f.tick<=event.tick+5000).flatMap(f=>rateChanges(recordedRates(f,slot),baseline).map(n=>Math.abs(n.delta))).sort((a,b)=>a-b)
 // Fixed for the entire event, so playback does not renormalize every frame.
 return Math.max(50,magnitudes[Math.floor(magnitudes.length*.95)]||0)
}
export function responseFrame(frames:Frame[],event:ReplayEvent,delay:number){return frames.find(f=>f.tick>=event.tick+delay*10000)}
