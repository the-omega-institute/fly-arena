import {useEffect,useMemo} from 'react'
import {Canvas,useThree} from '@react-three/fiber'
import {OrbitControls} from '@react-three/drei'
import * as THREE from 'three'
import type {NeuralGraph} from '../../types'
import type {AnatomySpace,SpatialNode} from './anatomy'
import {spatialNodes} from './anatomy'

export type BrainAngle='oblique'|'xy'|'xz'
function Camera({angle,reset}:{angle:BrainAngle;reset:number}){
  const {camera,controls,invalidate}=useThree()
  useEffect(()=>{
    const orbit=controls as unknown as {target:THREE.Vector3;update:()=>void}|null
    camera.up.set(0,angle==='xz'?0:1,angle==='xz'?1:0)
    camera.position.set(...(angle==='xy'?[0,0,2.4]:angle==='xz'?[0,-2.4,0]:[1.3,.7,2]) as [number,number,number])
    orbit?.target.set(0,0,0);camera.lookAt(0,0,0);orbit?.update();invalidate()
  },[angle,reset,camera,controls,invalidate])
  return null
}
function Connections({graph,space,focus}:{graph:NeuralGraph;space:AnatomySpace;focus:string|null}){
  const lines=useMemo(()=>{
    const byId=new Map(spatialNodes(graph,space,new Map()).map(n=>[n.id,n]));const positions:number[]=[],colors:number[]=[]
    for(const edge of graph.edges){
      if(edge.pre!==focus&&edge.post!==focus)continue
      const a=byId.get(edge.pre)?.position,b=byId.get(edge.post)?.position
      if(!a||!b||edge.pre===edge.post)continue
      positions.push(...a,...b)
      const color=new THREE.Color(edge.multiplier!==undefined&&Math.abs(edge.multiplier-1)>1e-8?'#f4cc7b':edge.weight===undefined?'#859890':edge.weight<0?'#e09aae':edge.weight>0?'#84cdb0':'#859890')
      colors.push(...color.toArray(),...color.toArray())
    }
    return {positions:new Float32Array(positions),colors:new Float32Array(colors)}
  },[graph,space,focus])
  return <lineSegments><bufferGeometry key={focus??'none'}><bufferAttribute attach="attributes-position" args={[lines.positions,3]}/><bufferAttribute attach="attributes-color" args={[lines.colors,3]}/></bufferGeometry><lineBasicMaterial vertexColors transparent opacity={.8}/></lineSegments>
}

export function AnatomicalBrainCanvas({space,nodes,graph,focus,onFocus,scale,angle,reset}:{space:AnatomySpace;nodes:SpatialNode[];graph:NeuralGraph;focus:string|null;onFocus:(id:string)=>void;scale:number;angle:BrainAngle;reset:number}){
  const neighbors=new Set(graph.edges.filter(e=>e.pre===focus||e.post===focus).flatMap(e=>[e.pre,e.post]))
  return <Canvas frameloop="demand" dpr={[1,1.5]} camera={{position:[1.3,.7,2],near:.01,far:30,fov:42}} gl={{antialias:true,alpha:false}}>
    <color attach="background" args={['#10241f']}/>
    <points raycast={()=>{}}><bufferGeometry><bufferAttribute attach="attributes-position" args={[space.positions,3]}/></bufferGeometry><pointsMaterial color="#82968a" size={1.3} sizeAttenuation={false} transparent opacity={.08} depthWrite={false}/></points>
    <Connections graph={graph} space={space} focus={focus}/>
    {nodes.map(node=>{
      if(!node.position||(node.activity===null&&!neighbors.has(node.id)&&node.id!==focus))return null
      const strength=node.activity===null?null:Math.max(0,Math.min(1,Math.log1p(Math.max(0,node.activity))/Math.log1p(Math.max(1,scale))))
      const color=strength===null?'#a3ada6':strength===0?'#4e8475':new THREE.Color().setHSL((145-strength*115)/360,.7,.62)
      return <group key={node.id} position={node.position}>
        <mesh onClick={event=>{event.stopPropagation();onFocus(node.id)}}><sphereGeometry args={[.022,10,8]}/><meshBasicMaterial color={color} wireframe={strength===null} depthTest={false}/></mesh>
        {strength!==null&&strength>0&&<mesh raycast={()=>{}}><sphereGeometry args={[.025+.04*strength,12,8]}/><meshBasicMaterial color={color} transparent opacity={.12+.4*strength} blending={THREE.AdditiveBlending} depthWrite={false} depthTest={false}/></mesh>}
        {node.id===focus&&<mesh raycast={()=>{}}><sphereGeometry args={[.029,12,8]}/><meshBasicMaterial color="#f4cc7b" wireframe depthTest={false}/></mesh>}
      </group>
    })}
    <OrbitControls makeDefault enableDamping={false} minDistance={.25} maxDistance={10}/>
    <Camera angle={angle} reset={reset}/>
  </Canvas>
}
