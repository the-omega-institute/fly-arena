import type {Frame,ReplayEvent,Scene}
  from '../../types'

export const replayInspectionSteps = [
  'individual',
  'outcome',
  'navigator',
  'detail',
  'disclosures',
] as const

export type ReplayInspectionStep = typeof replayInspectionSteps[number]

/** Select the recorded participant without inventing a fallback identity. */
export function selectedReplaySlot(scene:Pick<Scene,'flies'>,selectedId:string|undefined,current=0){
  const selected=scene.flies.findIndex(fly=>fly.id===selectedId)
  if(selected>=0)return selected
  return Math.min(Math.max(current,0),Math.max(0,scene.flies.length-1))
}

/** Keep the navigator chronological and remove duplicate event receipts. */
export function replayNavigatorEvents(events:ReplayEvent[],slot:number){
  const seen=new Set<string>()
  return events
    .filter(event=>event.slot===undefined||event.slot===slot||event.slots?.includes(slot))
    .filter(event=>{
      const key=JSON.stringify([event.type,event.tick,event.slot,event.food,event.objects,event.amount])
      if(seen.has(key))return false
      seen.add(key);return true
    })
    .sort((a,b)=>a.tick-b.tick)
}

/** Locate the first recorded sample at or after an event response time. */
export function sharedPlayheadSample(frames:Pick<Frame,'time'|'tick'>[],event:ReplayEvent,delayMs=0){
  if(!frames.length||!Number.isFinite(event.tick))return null
  const target=event.tick/10000+Math.max(0,delayMs)/1000
  let index=frames.findIndex(frame=>Number.isFinite(frame.time)&&frame.time>=target)
  if(index<0)index=frames.length-1
  const frame=frames[index]
  return Number.isFinite(frame.time)?{index,time:frame.time,eventTime:event.tick/10000}:null
}

export type RecordedOutcome={score:number|null;energy:number|null;duration:number|null;status:'recorded'|'partial'|'unavailable'}

/** Report only values present in the immutable replay samples. */
export function recordedOutcome(frames:Pick<Frame,'time'|'scores'|'energy'>[],slot:number,result?:{scores?:number[]}|null):RecordedOutcome{
  const last=frames.at(-1)
  const score=result?.scores?.[slot]??last?.scores?.[slot]
  const energy=last?.energy?.[slot]
  const duration=frames.length&&Number.isFinite(frames[0]?.time)&&Number.isFinite(last?.time)?Math.max(0,last!.time-frames[0].time):null
  const hasSample=frames.length>0
  return {score:typeof score==='number'&&Number.isFinite(score)?score:null,energy:typeof energy==='number'&&Number.isFinite(energy)?energy:null,duration,status:hasSample?'recorded':'unavailable'}
}

