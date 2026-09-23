import {useEffect,useMemo} from 'react'
import * as THREE from 'three'
import type {ArenaObstacle} from '../../types'
import {ArenaObstacles} from './obstacleGeometry'
import {useI18n} from '../../shared/i18n'
import {sceneThemes} from '../../shared/theme'

type HabitatProps={size:number;obstacles:ArenaObstacle[]}

function seeded(seed:number){
  let state=seed>>>0
  return ()=>{state=(1664525*state+1013904223)>>>0;return state/4294967296}
}

function proceduralTexture(kind:'soil'|'leaf'|'rock'|'fruit'){
  const width=64,height=64,data=new Uint8Array(width*height*4),random=seeded({soil:11,leaf:23,rock:37,fruit:53}[kind])
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const i=(y*width+x)*4
    let base:[number,number,number]=[225,225,225] // Neutral grain preserves the recorded material color.
    const grain=(random()-.5)*18
    if(kind==='leaf'){
      const vein=Math.abs(Math.sin((x+y)*.22)+.35*Math.sin((x-y)*.11))<.12
      if(vein)base=[244,244,244]
    }else if(kind==='fruit'&&random()<.08)base=[245,245,245]
    else if(kind==='rock'&&random()<.1)base=[195,195,195]
    else if(kind==='soil'&&random()<.1)base=[195,195,195]
    data[i]=Math.max(0,Math.min(255,base[0]+grain));data[i+1]=Math.max(0,Math.min(255,base[1]+grain));data[i+2]=Math.max(0,Math.min(255,base[2]+grain));data[i+3]=255
  }
  const texture=new THREE.DataTexture(data,width,height,THREE.RGBAFormat)
  texture.wrapS=THREE.RepeatWrapping;texture.wrapT=THREE.RepeatWrapping;texture.repeat.set(4,4);texture.colorSpace=THREE.SRGBColorSpace;texture.needsUpdate=true
  return texture
}

export function Habitat({size,obstacles}:HabitatProps){
  const {resolved}=useI18n(),tokens=sceneThemes[resolved]
  const textures=useMemo(()=>({soil:proceduralTexture('soil'),leaf:proceduralTexture('leaf'),rock:proceduralTexture('rock'),fruit:proceduralTexture('fruit')}),[])
  useEffect(()=>()=>Object.values(textures).forEach(texture=>texture.dispose()),[textures])
  useEffect(()=>{textures.soil.repeat.set(size/4,size/4)},[textures,size])
  return <>
    <mesh position={[0,0,-.12]} receiveShadow>
      <boxGeometry args={[size,size,.24]}/><meshStandardMaterial color={tokens.soil} map={textures.soil} roughness={1}/>
    </mesh>
    <ArenaObstacles obstacles={obstacles} color={tokens.obstacle} surfaces={textures}/>
  </>
}
