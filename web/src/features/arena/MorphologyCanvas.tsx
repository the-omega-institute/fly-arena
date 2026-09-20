import {useEffect,useMemo} from 'react'
import {Canvas,useThree} from '@react-three/fiber'
import {OrbitControls} from '@react-three/drei'
import * as THREE from 'three'
import type {Morphology} from './morphology'
import {morphologyActivity,morphologyBounds,regionColorMap} from './morphology'
import type {BrainAngle} from './AnatomicalBrainCanvas'

const vertex=`attribute float neuron; attribute vec3 tint; uniform sampler2D states; uniform float width; varying vec4 state; varying vec3 hue; varying float depth;
void main(){depth=position.z;state=texture2D(states,vec2((neuron+0.5)/width,0.5));hue=tint;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`
const fragment=`uniform float structure; uniform float clipDepth; varying vec4 state; varying vec3 hue; varying float depth;
void main(){if(depth>clipDepth)discard;bool recorded=state.g>0.5; float strength=state.r; vec3 c=hue;float alpha;
if(structure>0.5){alpha=state.b>0.5?0.65:0.32;}else if(recorded){alpha=0.07+0.88*strength; c=hue*(0.45+0.55*strength);}else{c=hue*0.45;alpha=0.075;}
gl_FragColor=vec4(c,alpha);
#include <colorspace_fragment>
}`
function Fibers({data,activity,scale,focus,onFocus,structure,wholeCns,angle,reset}:{data:Morphology;activity:Map<string,number>;scale:number;focus:string|null;onFocus:(id:string)=>void;structure:boolean;wholeCns:boolean;angle:BrainAngle;reset:number}){
 const {camera,controls,invalidate,size}=useThree()
 const resources=useMemo(()=>{
  const space=morphologyBounds(data,wholeCns),positions:number[]=[],tints:number[]=[],indices:number[]=[]
  const palette=regionColorMap(data),rgbCache=new Map([...palette].map(([id,c])=>[id,new THREE.Color(c).toArray()])),unassigned=new THREE.Color('#526b78').toArray()
  data.neurons.forEach((n,index)=>{for(let edge=0;edge<n.edges.length/2;edge++){const rgb=rgbCache.get(n.edge_regions?.[edge]??0)||unassigned;for(let end=0;end<2;end++){const i=n.edges[edge*2+end];for(let a=0;a<3;a++)positions.push((n.positions[i*3+a]-space.center[a])/space.extent);tints.push(...rgb);indices.push(index)}}})
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.setAttribute('tint',new THREE.Float32BufferAttribute(tints,3));geometry.setAttribute('neuron',new THREE.Float32BufferAttribute(indices,1));geometry.computeBoundingSphere()
  const texture=new THREE.DataTexture(new Uint8Array(data.neurons.length*4),data.neurons.length,1,THREE.RGBAFormat);texture.needsUpdate=true
  const material=new THREE.ShaderMaterial({vertexShader:vertex,fragmentShader:fragment,uniforms:{states:{value:texture},width:{value:data.neurons.length},structure:{value:0},clipDepth:{value:wholeCns?100:(space.high[2]-space.center[2])/space.extent}},transparent:true,depthWrite:false,blending:THREE.NormalBlending})
  return {geometry,texture,material,space}
 },[data,wholeCns])
 useEffect(()=>()=>{resources.geometry.dispose();resources.texture.dispose();resources.material.dispose()},[resources])
 useEffect(()=>{resources.texture.image.data.set(morphologyActivity(data.neurons,activity,scale,focus));resources.texture.needsUpdate=true;resources.material.uniforms.structure.value=structure?1:0;invalidate()},[resources,data,activity,scale,focus,structure,invalidate])
 useEffect(()=>{const orbit=controls as unknown as {target:THREE.Vector3;update:()=>void}|null;if(camera instanceof THREE.OrthographicCamera){const width=(resources.space.high[0]-resources.space.low[0])/resources.space.extent;const height=(resources.space.high[angle==='xz'?2:1]-resources.space.low[angle==='xz'?2:1])/resources.space.extent;camera.zoom=Math.min(size.width/(1.15*Math.max(.5,width)),size.height/(1.15*Math.max(.5,height)));camera.updateProjectionMatrix()}camera.up.set(0,angle==='xz'?0:1,angle==='xz'?1:0);camera.position.set(...(angle==='xz'?[0,-3.3,0]:angle==='xy'?[0,0,-3.3]:[.7,-.3,-3.3]) as [number,number,number]);orbit?.target.set(0,0,0);camera.lookAt(0,0,0);orbit?.update();invalidate()},[camera,controls,angle,reset,wholeCns,invalidate,size.width,size.height,resources])
 return <>
  <lineSegments geometry={resources.geometry} material={resources.material} onClick={event=>{if(event.index===undefined)return;event.stopPropagation();const i=resources.geometry.getAttribute('neuron').getX(event.index);onFocus(data.neurons[i].id)}}/>
 </>
}
export function MorphologyCanvas(props:Parameters<typeof Fibers>[0]){
 return <Canvas orthographic frameloop="demand" dpr={[1,1.5]} camera={{zoom:200,near:.01,far:30,position:[0,0,-3.3]}} gl={{antialias:true,alpha:false}} onCreated={({raycaster})=>{raycaster.params.Line.threshold=.006}}>
  <color attach="background" args={['#030909']}/>
  <OrbitControls makeDefault enableDamping={false} minDistance={.15} maxDistance={12}/>
  <Fibers {...props}/>
 </Canvas>
}
