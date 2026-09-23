import {useRef} from 'react'
import {useFrame,useThree} from '@react-three/fiber'
import type {Frame,Scene} from '../../types'
import type {OrbitControls} from 'three-stdlib'
import {recordedCameraTarget,translatedCameraPosition} from './followCamera'

export function ReplayCamera({scene,frame,next,alpha,selectedId,follow,overview,overviewTarget}:{scene?:Scene|null;frame?:Frame;next?:Frame;alpha:number;selectedId?:string;follow:boolean;overview:[number,number,number];overviewTarget?:[number,number,number]}){
 const {camera}=useThree()
 const initialized=useRef<string|null>(null)
 useFrame(state=>{
  const controls=state.controls as OrbitControls|null
  if(!controls?.target)return
  const slot=scene?.flies.findIndex(f=>f.id===selectedId)??-1
  const target=follow&&slot>=0?recordedCameraTarget(frame,next,alpha,slot):null
  // Wait for valid data while following, rather than following another fly.
  if(follow&&!target)return
  const mode=follow?`follow:${selectedId}`:`overview:${overview.join(',')}:${overviewTarget?.join(',')}`
  if(initialized.current!==mode){
   if(target){camera.position.set(target[0]+5,target[1]-7,target[2]+4);controls.target.set(...target)}
   else{camera.position.set(...overview);controls.target.set(...(overviewTarget||[0,0,scene?.habitat==='forest-floor' ? .25 : 0] as [number,number,number]))}
   initialized.current=mode
  }else if(target){
   camera.position.set(...translatedCameraPosition(camera.position.toArray(),controls.target.toArray(),target))
   controls.target.set(...target)
  }else return
  controls.update()
 })
 return null
}
