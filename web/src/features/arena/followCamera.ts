import type {Frame} from '../../types'

/** Same linear position interpolation used by the recorded body renderer. */
export function recordedCameraTarget(frame:Frame|undefined,next:Frame|undefined,alpha:number,slot:number):[number,number,number]|null{
 const p=frame?.positions?.[slot]
 if(!p||p.length<3||!p.slice(0,3).every(Number.isFinite))return null
 const candidate=next?.positions?.[slot]
 const n=candidate&&candidate.length>=3&&candidate.slice(0,3).every(Number.isFinite)?candidate:p
 const amount=Number.isFinite(alpha)?Math.min(1,Math.max(0,alpha)):0
 return [p[0]+(n[0]-p[0])*amount,p[1]+(n[1]-p[1])*amount,p[2]+(n[2]-p[2])*amount]
}

/** Translate camera and orbit target together so manual orbit/zoom is retained. */
export function translatedCameraPosition(camera:readonly number[],previous:readonly number[],target:readonly number[]):[number,number,number]{
 return [camera[0]+target[0]-previous[0],camera[1]+target[1]-previous[1],camera[2]+target[2]-previous[2]]
}
