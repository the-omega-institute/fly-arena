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

export type SceneFraming={position:[number,number,number];target:[number,number,number];distance:number;span:number}
/** Fit all eight bounds corners at the actual viewport aspect; z remains world-up. */
export function sceneFraming(bounds:{min:readonly number[];max:readonly number[]},aspect:number,fov=40,overhead=false):SceneFraming{
 const {min,max}=bounds,target=min.map((value,axis)=>(value+max[axis])/2) as [number,number,number]
 const direction=overhead?[.28,-.38,.88]:[.46,-.62,.64],length=Math.hypot(...direction)
 const backward=direction.map(value=>value/length),horizontal=Math.hypot(backward[0],backward[1])
 const right=[-backward[1]/horizontal,backward[0]/horizontal,0]
 const up=[-backward[2]*right[1],backward[2]*right[0],horizontal]
 const tanY=Math.tan(fov*Math.PI/360),tanX=tanY*Math.max(.1,aspect)
 let distance=0
 for(const x of [min[0],max[0]])for(const y of [min[1],max[1]])for(const z of [min[2],max[2]]){
  const p=[x-target[0],y-target[1],z-target[2]],dot=(v:number[])=>p.reduce((sum,value,axis)=>sum+value*v[axis],0)
  distance=Math.max(distance,dot(backward)+1.14*Math.max(Math.abs(dot(right))/tanX,Math.abs(dot(up))/tanY))
 }
 const span=Math.max(...max.map((value,axis)=>value-min[axis]),1)
 distance=Math.max(distance,span)
 return {position:target.map((value,axis)=>value+backward[axis]*distance) as [number,number,number],target,distance,span}
}

/** Millimeter grid with bounded density, shared across plain arena sizes. */
export function sceneGrid(size:number){
 const step=10**Math.floor(Math.log10(Math.max(1,size/24))),ratio=size/24/step
 const cell=step*(ratio>=5?5:ratio>=2?2:1)
 return {cell,section:cell*5,fade:size*2}
}
