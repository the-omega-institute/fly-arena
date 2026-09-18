import type {ArenaObstacle} from '../../types'

export type ObstacleGeometry={
  position:[number,number,number]
  size:[number,number,number]
  quaternion:[number,number,number,number]
  shape:'box'|'ellipsoid'
}

/** Converts backend center/full-size and wxyz rotation into Three-friendly args. */
export function obstacleGeometry(obstacle:ArenaObstacle):ObstacleGeometry{
  const position=[obstacle.position[0]??0,obstacle.position[1]??0,obstacle.position[2]??0] as [number,number,number]
  const size=[obstacle.size[0]??1,obstacle.size[1]??1,obstacle.size[2]??1] as [number,number,number]
  const w=obstacle.quaternion?.[0]??1
  const x=obstacle.quaternion?.[1]??0
  const y=obstacle.quaternion?.[2]??0
  const z=obstacle.quaternion?.[3]??0
  const length=Math.hypot(w,x,y,z)
  const quaternion=length>Number.EPSILON?[x/length,y/length,z/length,w/length]:[0,0,0,1]
  return {position,size,quaternion:quaternion as [number,number,number,number],shape:obstacle.shape==='ellipsoid'?'ellipsoid':'box'}
}
