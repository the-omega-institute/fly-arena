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
if(structure>0.5){alpha=state.b>0.5?0.65:0.32;}else if(recorded){alpha=0.06+0.6*strength; c=hue*(0.3+0.7*strength);}else{c=hue*0.35;alpha=0.06;}
gl_FragColor=vec4(c,alpha);
#include <colorspace_fragment>
}`
// Screen-space ribbons follow the same SWC segments: no point sprites or new anatomy.
const ribbonVertex=`attribute vec3 start; attribute vec3 end; attribute float neuron; attribute vec3 tint;
uniform sampler2D states; uniform float width; uniform vec2 viewport;
varying vec4 state; varying vec3 hue; varying float depth; varying float across;
void main(){state=texture2D(states,vec2((neuron+0.5)/width,0.5));hue=tint;across=position.y;depth=0.0;
if(state.g<0.5||state.r<0.004){gl_Position=vec4(2.0,2.0,2.0,1.0);return;}
vec4 a=projectionMatrix*modelViewMatrix*vec4(start,1.0),b=projectionMatrix*modelViewMatrix*vec4(end,1.0);
vec2 d=(b.xy/b.w-a.xy/a.w)*viewport;vec2 normal=vec2(-d.y,d.x)/max(length(d),0.0001);
vec4 p=mix(a,b,position.x);p.xy+=normal*position.y*(1.0+2.0*state.r)/viewport*p.w;
depth=mix(start.z,end.z,position.x);gl_Position=p;}`
const ribbonFragment=`uniform float clipDepth;varying vec4 state;varying vec3 hue;varying float depth;varying float across;
void main(){if(depth>clipDepth||state.g<0.5||state.r<0.004)discard;
float alpha=state.r*(1.0-smoothstep(0.25,1.0,abs(across)))*0.8;
gl_FragColor=vec4(hue,alpha);
#include <colorspace_fragment>
}`
function Fibers({data,activity,scale,focus,onFocus,structure,wholeCns,angle,reset,changeMode=false,recordedIds=[],zoomId}:{data:Morphology;activity:Map<string,number>;scale:number;focus:string|null;onFocus:(id:string)=>void;structure:boolean;wholeCns:boolean;angle:BrainAngle;reset:number;changeMode?:boolean;recordedIds?:string[];zoomId?:string|null}){
 const {camera,controls,invalidate,size}=useThree()
 const recordingKey=recordedIds.slice().sort().join(',')
 const resources=useMemo(()=>{
  const space=morphologyBounds(data,wholeCns),positions:number[]=[],tints:number[]=[],indices:number[]=[]
  const palette=regionColorMap(data),rgbCache=new Map([...palette].map(([id,c])=>[id,new THREE.Color(c).toArray()])),unassigned=new THREE.Color('#526b78').toArray()
  data.neurons.forEach((n,index)=>{for(let edge=0;edge<n.edges.length/2;edge++){const rgb=rgbCache.get(n.edge_regions?.[edge]??0)||unassigned;for(let end=0;end<2;end++){const i=n.edges[edge*2+end];for(let a=0;a<3;a++)positions.push((n.positions[i*3+a]-space.center[a])/space.extent);tints.push(...rgb);indices.push(index)}}})
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.setAttribute('tint',new THREE.Float32BufferAttribute(tints,3));geometry.setAttribute('neuron',new THREE.Float32BufferAttribute(indices,1));geometry.computeBoundingSphere()
  const texture=new THREE.DataTexture(new Uint8Array(data.neurons.length*4),data.neurons.length,1,THREE.RGBAFormat);texture.needsUpdate=true
  const uniforms={states:{value:texture},width:{value:data.neurons.length},structure:{value:0},viewport:{value:new THREE.Vector2()},clipDepth:{value:wholeCns?100:(space.high[2]-space.center[2])/space.extent}}
  const material=new THREE.ShaderMaterial({vertexShader:vertex,fragmentShader:fragment,uniforms,transparent:true,depthWrite:false,blending:THREE.NormalBlending})
  const recorded=new Set(recordingKey.split(','));const ribbon=new THREE.InstancedBufferGeometry(),starts:number[]=[],ends:number[]=[],colors:number[]=[],neurons:number[]=[]
  for(let i=0;i<positions.length;i+=6){if(!recorded.has(data.neurons[indices[i/3]].id))continue;starts.push(...positions.slice(i,i+3));ends.push(...positions.slice(i+3,i+6));colors.push(...tints.slice(i,i+3));neurons.push(indices[i/3])}
  ribbon.setAttribute('position',new THREE.Float32BufferAttribute([0,-1,0,1,-1,0,0,1,0,0,1,0,1,-1,0,1,1,0],3))
  ribbon.setAttribute('start',new THREE.InstancedBufferAttribute(new Float32Array(starts),3));ribbon.setAttribute('end',new THREE.InstancedBufferAttribute(new Float32Array(ends),3));ribbon.setAttribute('tint',new THREE.InstancedBufferAttribute(new Float32Array(colors),3));ribbon.setAttribute('neuron',new THREE.InstancedBufferAttribute(new Float32Array(neurons),1));ribbon.instanceCount=neurons.length
  const ribbonMaterial=new THREE.ShaderMaterial({vertexShader:ribbonVertex,fragmentShader:ribbonFragment,uniforms,transparent:true,depthWrite:false,depthTest:false,side:THREE.DoubleSide,blending:THREE.NormalBlending})
  return {geometry,texture,material,ribbon,ribbonMaterial,space}
 },[data,wholeCns,recordingKey])
 useEffect(()=>()=>{resources.geometry.dispose();resources.texture.dispose();resources.material.dispose();resources.ribbon.dispose();resources.ribbonMaterial.dispose()},[resources])
 useEffect(()=>{resources.texture.image.data.set(morphologyActivity(data.neurons,activity,scale,focus,changeMode));resources.texture.needsUpdate=true;resources.material.uniforms.structure.value=structure?1:0;resources.material.uniforms.viewport.value.set(size.width,size.height);invalidate()},[resources,data,activity,scale,focus,structure,changeMode,invalidate,size])
 useEffect(()=>{
  const orbit=controls as unknown as {target:THREE.Vector3;update:()=>void}|null,space=resources.space
  const selected=data.neurons.find(n=>n.id===zoomId),low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity]
  if(selected)for(let i=0;i<selected.positions.length;i+=3){if(!wholeCns&&selected.positions[i+2]>space.high[2])continue;for(let a=0;a<3;a++){low[a]=Math.min(low[a],selected.positions[i+a]);high[a]=Math.max(high[a],selected.positions[i+a])}}
  const focused=Number.isFinite(low[0]),target=new THREE.Vector3(...(focused?low.map((v,i)=>((v+high[i])/2-space.center[i])/space.extent):[0,0,0]) as [number,number,number])
  const bounds=focused?{low,high}:space
  if(camera instanceof THREE.OrthographicCamera){const width=(bounds.high[0]-bounds.low[0])/space.extent,height=(bounds.high[angle==='xz'?2:1]-bounds.low[angle==='xz'?2:1])/space.extent;camera.zoom=Math.min(size.width/(1.2*Math.max(.18,width)),size.height/(1.2*Math.max(.18,height)));camera.updateProjectionMatrix()}
  camera.up.set(0,angle==='xz'?0:1,angle==='xz'?1:0);camera.position.set(...(angle==='xz'?[0,-3.3,0]:angle==='xy'?[0,0,-3.3]:[.7,-.3,-3.3]) as [number,number,number]);camera.position.add(target);orbit?.target.copy(target);camera.lookAt(target);orbit?.update();invalidate()
 },[camera,controls,angle,reset,wholeCns,invalidate,size.width,size.height,resources,data,zoomId])
 return <>
  <lineSegments geometry={resources.geometry} material={resources.material} onClick={event=>{if(event.index===undefined)return;event.stopPropagation();const i=resources.geometry.getAttribute('neuron').getX(event.index);onFocus(data.neurons[i].id)}}/>
  {!structure&&<mesh geometry={resources.ribbon} material={resources.ribbonMaterial} frustumCulled={false} renderOrder={2} raycast={()=>{}}/>}
 </>
}
export function MorphologyCanvas(props:Parameters<typeof Fibers>[0]){
 return <Canvas orthographic frameloop="demand" dpr={[1,1.5]} camera={{zoom:200,near:.01,far:30,position:[0,0,-3.3]}} gl={{antialias:true,alpha:false}} onCreated={({raycaster})=>{raycaster.params.Line.threshold=.006}}>
  <color attach="background" args={['#030909']}/>
  <OrbitControls makeDefault enableDamping={false} minDistance={.15} maxDistance={12}/>
  <Fibers {...props}/>
 </Canvas>
}
