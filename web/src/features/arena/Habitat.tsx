import {useEffect,useMemo} from 'react'
import * as THREE from 'three'
import type {ArenaObstacle} from '../../types'
import {obstacleGeometry} from './obstacleGeometry'

type HabitatProps={size:number;obstacles:ArenaObstacle[]}

const materialColors={leaf:'#607d54',rock:'#75624e',fruit:'#b86b3c'} as const

function HabitatObstacle({obstacle,surface}:{obstacle:ArenaObstacle;surface:THREE.Texture}){
  const geometry=obstacleGeometry(obstacle)
  const {size,position,quaternion}=geometry
  const color=obstacle.color||materialColors[obstacle.material||'rock']
  return <mesh position={position} quaternion={quaternion} scale={geometry.shape==='ellipsoid'?[size[0]/2,size[1]/2,size[2]/2]:undefined} castShadow receiveShadow>
    {geometry.shape==='ellipsoid'?<sphereGeometry args={[1,32,20]}/>:<boxGeometry args={size}/>}<meshStandardMaterial color={color} map={surface} roughness={obstacle.material==='fruit'?.48:.88} metalness={.015}/>
  </mesh>
}

function seeded(seed:number){
  let state=seed>>>0
  return ()=>{state=(1664525*state+1013904223)>>>0;return state/4294967296}
}

function proceduralTexture(kind:'soil'|'leaf'|'rock'|'fruit'){
  const width=64,height=64,data=new Uint8Array(width*height*4),random=seeded({soil:11,leaf:23,rock:37,fruit:53}[kind])
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const i=(y*width+x)*4
    let base:[number,number,number]=kind==='soil'?[116,99,78]:kind==='leaf'?[93,123,79]:kind==='rock'?[118,99,78]:[170,92,52]
    const grain=(random()-.5)*18
    if(kind==='leaf'){
      const vein=Math.abs(Math.sin((x+y)*.22)+.35*Math.sin((x-y)*.11))<.12
      if(vein)base=[116,147,92]
    }else if(kind==='fruit'&&random()<.08)base=[213,133,68]
    else if(kind==='rock'&&random()<.1)base=[83,70,57]
    else if(kind==='soil'&&random()<.1)base=[82,70,53]
    data[i]=Math.max(0,Math.min(255,base[0]+grain));data[i+1]=Math.max(0,Math.min(255,base[1]+grain));data[i+2]=Math.max(0,Math.min(255,base[2]+grain));data[i+3]=255
  }
  const texture=new THREE.DataTexture(data,width,height,THREE.RGBAFormat)
  texture.wrapS=THREE.RepeatWrapping;texture.wrapT=THREE.RepeatWrapping;texture.repeat.set(4,4);texture.colorSpace=THREE.SRGBColorSpace;texture.needsUpdate=true
  return texture
}

export function Habitat({size,obstacles}:HabitatProps){
  const textures=useMemo(()=>({soil:proceduralTexture('soil'),leaf:proceduralTexture('leaf'),rock:proceduralTexture('rock'),fruit:proceduralTexture('fruit')}),[])
  useEffect(()=>()=>Object.values(textures).forEach(texture=>texture.dispose()),[textures])
  return <>
    <mesh position={[0,0,-.12]} receiveShadow>
      <boxGeometry args={[size,size,.24]}/><meshStandardMaterial color="#665947" map={textures.soil} roughness={1}/>
    </mesh>
    <mesh position={[0,0,.012]} rotation={[0,0,0]} receiveShadow>
      <planeGeometry args={[size,size]}/><meshStandardMaterial color="#756652" map={textures.soil} roughness={1}/>
    </mesh>
    {obstacles.map((obstacle,index)=><HabitatObstacle key={index} obstacle={obstacle} surface={textures[obstacle.material||'rock']}/>)}
  </>
}
