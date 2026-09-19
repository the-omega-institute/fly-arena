import type {Frame,ReplayEvent} from '../../types'

export type LifeEventKind = 'all'|'food'|'contact'|'outcome'
export const LIFE_EVENT_PAGE_SIZE = 12
const kinds:Record<Exclude<LifeEventKind,'all'>,string[]> = {
  food:['odor_detected','visual_target_detected','food_contact','intake'],
  contact:['environment_contact','contact'],
  outcome:['exit'],
}

export function lifeEvents(events:ReplayEvent[],slot:number,kind:LifeEventKind='all') {
  return events.filter(event=>(event.slot===undefined||event.slot===slot)&&
    (kind==='all'||kinds[kind].includes(event.type))).sort((a,b)=>a.tick-b.tick)
}

export function lifeEventPage(events:ReplayEvent[],page:number) {
  const pages=Math.max(1,Math.ceil(events.length/LIFE_EVENT_PAGE_SIZE))
  const current=Math.max(0,Math.min(page,pages-1)),start=current*LIFE_EVENT_PAGE_SIZE
  return {page:current,pages,start,rows:events.slice(start,start+LIFE_EVENT_PAGE_SIZE)}
}

export function lifeEventPageAtTime(events:ReplayEvent[],time:number) {
  const next=events.findIndex(event=>event.tick/10000>time)
  const current=next===-1?events.length-1:Math.max(0,next-1)
  return Math.floor(Math.max(0,current)/LIFE_EVENT_PAGE_SIZE)
}

export function eventSampleWindow(frames:Frame[],event:ReplayEvent) {
  if(!frames.length)return null
  let before=frames[0]
  for(const candidate of frames){
    if(candidate.tick<=event.tick)before=candidate
    else return {before,after:candidate}
  }
  // A final event has no subsequent record: keep the actual final sample.
  return {before,after:frames[frames.length-1]}
}
