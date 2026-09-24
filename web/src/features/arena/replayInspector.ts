import type {Frame,Scene}
  from '../../types'

type ScreenRect={left:number;right:number;top:number;bottom:number}
/** Hide screen-space labels outside the scene or underneath its measured HUD. */
export function replayLabelHidden(label:ScreenRect,canvas:ScreenRect,hud?:ScreenRect|null){
  return label.left<canvas.left||label.right>canvas.right||label.top<canvas.top||label.bottom>canvas.bottom||
    !!(hud&&label.left<hud.right+4&&label.right>hud.left-4&&label.top<hud.bottom+4&&label.bottom>hud.top-4)
}

/** Select the recorded participant without inventing a fallback identity. */
export function selectedReplaySlot(scene:Pick<Scene,'flies'>,selectedId:string|undefined,current=0){
  const selected=scene.flies.findIndex(fly=>fly.id===selectedId)
  if(selected>=0)return selected
  return Math.min(Math.max(current,0),Math.max(0,scene.flies.length-1))
}

export function replayOutcomeLabel(outcome:string){
 return ({draw:'Replay outcome · draw',win:'Replay outcome · win',solo:'Replay outcome · solo'} as Record<string,string>)[outcome]||outcome
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
