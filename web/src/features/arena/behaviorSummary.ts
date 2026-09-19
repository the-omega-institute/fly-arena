import type {Frame,ReplayEvent} from '../../types'

export type BehaviorChapter = {
  start:number;end:number;path:number|null;displacement:number|null;intake:number|null;
  foodContacts:number;environmentContacts:number;flyContacts:number;exits:number;
}

/** Partition consecutive recorded samples. Boundaries use actual timestamps;
 * every movement segment and event belongs to exactly one chapter. */
export function behaviorChapters(frames:Frame[],events:ReplayEvent[],slot:number):BehaviorChapter[] {
  if(frames.length<2)return []
  const result:BehaviorChapter[]=[]
  let first=0
  for(let last=1;last<frames.length;last++){
    if(frames[last].time-frames[first].time<5&&last<frames.length-1)continue
    const a=frames[first],b=frames[last]
    const xy=(f:Frame)=>{
      const p=f.positions?.[slot]
      return p&&Number.isFinite(p[0])&&Number.isFinite(p[1])?p:null
    }
    let path:number|null=0
    for(let i=first+1;i<=last;i++){
      const p=xy(frames[i-1]),q=xy(frames[i])
      if(!p||!q){path=null;break}
      path+=Math.hypot(q[0]-p[0],q[1]-p[1])
    }
    const p=xy(a),q=xy(b),before=a.scores?.[slot],after=b.scores?.[slot]
    const recorded=events.filter(e=>
      (e.slot===undefined?(e.slots?.includes(slot)??true):e.slot===slot)&&
      (first===0?e.tick>=a.tick:e.tick>a.tick)&&e.tick<=b.tick)
    result.push({start:a.time,end:b.time,path,
      displacement:p&&q?Math.hypot(q[0]-p[0],q[1]-p[1]):null,
      intake:before!==undefined&&after!==undefined&&Number.isFinite(before)&&Number.isFinite(after)?after-before:null,
      foodContacts:recorded.filter(e=>e.type==='food_contact').length,
      environmentContacts:recorded.filter(e=>e.type==='environment_contact').length,
      flyContacts:recorded.filter(e=>e.type==='contact').length,
      exits:recorded.filter(e=>e.type==='exit').length})
    first=last
  }
  return result
}
