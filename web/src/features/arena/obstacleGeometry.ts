import {createElement,useLayoutEffect,useMemo,useRef} from 'react'
import * as THREE from 'three'
import type {ArenaGeometryContract,ArenaObstacle} from '../../types'

export const arenaGeometryContract: ArenaGeometryContract = {id:'arena-geometry-v1',units:'mm',worldAxes:{x:'east',y:'north',z:'up'},quaternionOrder:'wxyz'}

export type ObstacleGeometry={
  position:[number,number,number]
  size:[number,number,number]
  quaternion:[number,number,number,number]
  shape:'box'|'ellipsoid'
}

const finite=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value)
const vector=(value:unknown,length:number):value is number[]=>Array.isArray(value)&&value.length===length&&value.every(finite)

/** Strict boundary validator shared by map and research scene consumers. */
export function validateObstacleGeometry(value:unknown):value is ArenaObstacle{
 if(!value||typeof value!=='object')return false
 const obstacle=value as Record<string,unknown>
 if(!vector(obstacle.position,3)||!vector(obstacle.size,3)||obstacle.size.some(n=>n<=0))return false
 if(obstacle.shape!==undefined&&obstacle.shape!=='box'&&obstacle.shape!=='ellipsoid')return false
 if(obstacle.quaternion!==undefined&&(!vector(obstacle.quaternion,4)||Math.hypot(...obstacle.quaternion)===0))return false
 if(obstacle.material!==undefined&&!['leaf','rock','fruit'].includes(String(obstacle.material)))return false
 if(obstacle.color!==undefined&&(typeof obstacle.color!=='string'||!obstacle.color))return false
 return true
}

/** Convert MuJoCo wxyz to three.js xyzw after strict validation. */
export function normalizeObstacleGeometry(value:unknown):ObstacleGeometry{
 if(!validateObstacleGeometry(value))throw new Error('Invalid arena obstacle geometry')
 const obstacle=value as ArenaObstacle
 const q=obstacle.quaternion||[1,0,0,0],length=Math.hypot(...q)
 return {position:[...obstacle.position] as [number,number,number],size:[...obstacle.size] as [number,number,number],quaternion:[q[1]/length,q[2]/length,q[3]/length,q[0]/length],shape:obstacle.shape||'box'}
}

/** Backend centers/full diameters and wxyz rotations, in the recorded world axes. */
export function obstacleGeometry(obstacle:ArenaObstacle):ObstacleGeometry{
  const position=[obstacle.position[0]??0,obstacle.position[1]??0,obstacle.position[2]??0] as [number,number,number]
  const size=[obstacle.size[0]??1,obstacle.size[1]??1,obstacle.size[2]??1] as [number,number,number]
  const w=obstacle.quaternion?.[0]??1,x=obstacle.quaternion?.[1]??0,y=obstacle.quaternion?.[2]??0,z=obstacle.quaternion?.[3]??0
  const length=Math.hypot(w,x,y,z)
  const quaternion=length>Number.EPSILON?[x/length,y/length,z/length,w/length]:[0,0,0,1]
  return {position,size,quaternion:quaternion as [number,number,number,number],shape:obstacle.shape==='ellipsoid'?'ellipsoid':'box'}
}

const materialColors={leaf:'#607d54',rock:'#75624e',fruit:'#b86b3c'} as const
type ObstacleBatch={shape:ObstacleGeometry['shape'];material?:ArenaObstacle['material'];items:{geometry:ObstacleGeometry;color:string}[]}
export function obstacleBatches(obstacles:ArenaObstacle[],fallback:string):ObstacleBatch[]{
  const batches=new Map<string,ObstacleBatch>()
  for(const obstacle of obstacles){
    const geometry=obstacleGeometry(obstacle),key=`${geometry.shape}:${obstacle.material||'plain'}`
    if(!batches.has(key))batches.set(key,{shape:geometry.shape,material:obstacle.material,items:[]})
    batches.get(key)!.items.push({geometry,color:obstacle.color||(obstacle.material?materialColors[obstacle.material]:fallback)})
  }
  return [...batches.values()]
}

/** Unit box / unit-diameter sphere: instance scale always equals recorded full size. */
export function obstacleMatrix(geometry:ObstacleGeometry){
  return new THREE.Matrix4().compose(new THREE.Vector3(...geometry.position),new THREE.Quaternion(...geometry.quaternion),new THREE.Vector3(...geometry.size))
}

function ObstacleInstances({batch,surface}:{batch:ObstacleBatch;surface?:THREE.Texture}){
  const ref=useRef<THREE.InstancedMesh>(null)
  useLayoutEffect(()=>{
    const mesh=ref.current
    if(!mesh)return
    batch.items.forEach(({geometry,color},index)=>{mesh.setMatrixAt(index,obstacleMatrix(geometry));mesh.setColorAt(index,new THREE.Color(color))})
    mesh.instanceMatrix.needsUpdate=true
    if(mesh.instanceColor)mesh.instanceColor.needsUpdate=true
    // Recompute after layout/map changes; stale bounds would hide entire wall batches.
    mesh.computeBoundingBox();mesh.computeBoundingSphere()
  },[batch])
  return createElement('instancedMesh',{ref,args:[undefined,undefined,batch.items.length],castShadow:true,receiveShadow:true},
    createElement(batch.shape==='ellipsoid'?'sphereGeometry':'boxGeometry',{args:batch.shape==='ellipsoid'?[.5,32,20]:[1,1,1]}),
    createElement('meshStandardMaterial',{color:'#ffffff',map:surface,roughness:batch.material==='fruit'?.56:.88,metalness:0}))
}

/** Shared by habitat and plain arenas; colors do not split otherwise compatible batches. */
export function ArenaObstacles({obstacles,color,surfaces}:{obstacles:ArenaObstacle[];color:string;surfaces?:Partial<Record<NonNullable<ArenaObstacle['material']>,THREE.Texture>>}){
  const batches=useMemo(()=>obstacleBatches(obstacles,color),[obstacles,color])
  return createElement('group',null,...batches.map(batch=>createElement(ObstacleInstances,{key:`${batch.shape}:${batch.material||'plain'}:${batch.items.length}`,batch,surface:batch.material?surfaces?.[batch.material]:undefined})))
}

export type ArenaBounds={min:[number,number,number];max:[number,number,number]}
export type ArenaGeometry={size:number;obstacles:ArenaObstacle[];food:{position:number[]}[]}
export function arenaBounds(scene:ArenaGeometry):ArenaBounds{
  const min:[number,number,number]=[-scene.size/2,-scene.size/2,0],max:[number,number,number]=[scene.size/2,scene.size/2,0]
  const include=(position:number[],extent:number[])=>{for(let axis=0;axis<3;axis++){min[axis]=Math.min(min[axis],position[axis]-extent[axis]);max[axis]=Math.max(max[axis],position[axis]+extent[axis])}}
  for(const obstacle of scene.obstacles){
    const geometry=obstacleGeometry(obstacle),rotation=new THREE.Matrix4().makeRotationFromQuaternion(new THREE.Quaternion(...geometry.quaternion)).elements
    const extent=[0,1,2].map(axis=>{
      const components=[0,1,2].map(local=>rotation[local*4+axis]*geometry.size[local]/2)
      return geometry.shape==='ellipsoid'?Math.hypot(...components):components.reduce((sum,value)=>sum+Math.abs(value),0)
    })
    include(geometry.position,extent)
  }
  for(const food of scene.food)include([food.position[0],food.position[1],food.position[2]??.15],[.65,.65,.65])
  return {min,max}
}
