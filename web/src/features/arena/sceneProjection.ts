import {Vector3} from 'three'
import type {ArenaLayout,ArenaObstacle,Frame,Scene} from '../../types'
import {arenaBounds,obstacleGeometry,obstacleMatrix,validateObstacleGeometry} from './obstacleGeometry'

export type PlanWorld=(Scene|ArenaLayout)&{id?:string;spawns?:number[][]}
export type PlanPoint=[number,number]
const finite=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n)
const xy=(p:unknown):p is number[]=>Array.isArray(p)&&p.length>=2&&p.every(finite)
export const planDefault=(world?:PlanWorld|null)=>['maze','labyrinth','switchback'].includes(world?.id||'')||world?.task?.id==='maze-arrival-v1'?'2d':'3d'
export function validPlanWorld(world?:PlanWorld|null):world is PlanWorld{
 return !!world&&finite(world.size)&&world.size>0&&Array.isArray(world.obstacles)&&world.obstacles.every(validateObstacleGeometry)&&Array.isArray(world.food)&&world.food.every(f=>!!f&&xy(f.position))
}

/** Orthographic footprint of all eight corners; tilted boxes need a convex hull. */
function hull(points:PlanPoint[]):PlanPoint[]{
 const sorted=points.sort((a,b)=>a[0]-b[0]||a[1]-b[1]),cross=(a:PlanPoint,b:PlanPoint,c:PlanPoint)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
 const half=(list:PlanPoint[])=>{const result:PlanPoint[]=[];for(const p of list){while(result.length>1&&cross(result[result.length-2],result[result.length-1],p)<=0)result.pop();result.push(p)}return result.slice(0,-1)}
 return [...half(sorted),...half([...sorted].reverse())]
}
export function projectObstacle(obstacle:ArenaObstacle){
 const geometry=obstacleGeometry(obstacle),matrix=obstacleMatrix(geometry)
 if(geometry.shape==='box'){
  const points:PlanPoint[]=[]
  for(const x of [-.5,.5])for(const y of [-.5,.5])for(const z of [-.5,.5]){const p=new Vector3(x,y,z).applyMatrix4(matrix);points.push([p.x,p.y])}
  return {shape:'box' as const,points:hull(points)}
 }
 // Eigenvalues of the projected ellipsoid covariance give its exact silhouette.
 const e=matrix.elements,a=(e[0]**2+e[4]**2+e[8]**2)/4,b=(e[0]*e[1]+e[4]*e[5]+e[8]*e[9])/4,d=(e[1]**2+e[5]**2+e[9]**2)/4,delta=Math.hypot(a-d,2*b)
 return {shape:'ellipsoid' as const,center:geometry.position.slice(0,2) as PlanPoint,rx:Math.sqrt(Math.max(0,(a+d+delta)/2)),ry:Math.sqrt(Math.max(0,(a+d-delta)/2)),angle:Math.atan2(2*b,a-d)*90/Math.PI}
}
export function planPosition(frame:Frame|undefined,next:Frame|undefined,alpha:number,slot:number):PlanPoint|null{
 const amount=finite(alpha)?Math.max(0,Math.min(1,alpha)):0,p=frame?.positions?.[slot],n=next?.positions?.[slot]
 if(amount===1&&next)return finite(next.time)&&xy(n)?[n[0],n[1]]:null
 if(!frame||!finite(frame.time)||!xy(p))return null
 if(amount===0)return [p[0],p[1]]
 if(!next||!finite(next.time)||!xy(n)||next.time<=frame.time)return null
 return [p[0]+(n[0]-p[0])*amount,p[1]+(n[1]-p[1])*amount]
}
export function playbackTime(frame?:Frame,next?:Frame,alpha=0){
 if(!frame||!finite(frame.time))return null
 return frame.time+(next&&finite(next.time)&&next.time>frame.time?(next.time-frame.time)*Math.max(0,Math.min(1,finite(alpha)?alpha:0)):0)
}
/** Missing samples break paths; no extrapolation or future trail is displayed. */
export function planTrails(frames:Frame[],slot:number,time:number|null):PlanPoint[][]{
 const segments:PlanPoint[][]=[];let segment:PlanPoint[]=[]
 if(time===null)return segments
 for(let i=0;i<frames.length;i++){
  const frame=frames[i],p=frame.positions?.[slot],previous=frames[i-1]
  if(!finite(frame.time)||previous&&frame.time<=previous.time){segment=[];continue}
  if(frame.time>time){
   if(previous&&segment.length&&previous.time<time){const point=planPosition(previous,frame,(time-previous.time)/(frame.time-previous.time),slot);if(point)segment.push(point)}
   break
  }
  if(!xy(p)){segment=[];continue}
  if(!segment.length){segment=[];segments.push(segment)}
  segment.push([p[0],p[1]])
 }
 return segments
}
export function planFood(food:PlanWorld['food'][number],index:number,recorded:boolean,frame?:Frame){
 const amount=recorded?frame?.food?.[index]:food.initial
 return finite(amount)&&amount>=0?amount:null
}
export function planBounds(world:PlanWorld,frames:Frame[]){
 const {min,max}=arenaBounds(world)
 for(const p of [...(Array.isArray(world.spawns)?world.spawns:[]),...frames.flatMap(f=>f.positions||[])])if(xy(p)){min[0]=Math.min(min[0],p[0]);min[1]=Math.min(min[1],p[1]);max[0]=Math.max(max[0],p[0]);max[1]=Math.max(max[1],p[1])}
 const padding=Math.max(max[0]-min[0],max[1]-min[1])*.07
 return [min[0]-padding,-max[1]-padding,max[0]-min[0]+2*padding,max[1]-min[1]+2*padding]
}
