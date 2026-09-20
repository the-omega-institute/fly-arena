import {useEffect,useMemo} from 'react'
import {Canvas,useThree} from '@react-three/fiber'
import {OrbitControls} from '@react-three/drei'
import * as THREE from 'three'
import type {Morphology,NeuronMorphology} from './morphology'
import {morphologyActivity,morphologyBounds} from './morphology'
import type {BrainAngle} from './AnatomicalBrainCanvas'

function color(n:NeuronMorphology){
 const group=n.class||n.superclass||''
 if(/olfactory|ALPN|ALLN/.test(group))return '#50ecae'
 if(/Kenyon|MBON/.test(group))return '#ff76c8'
 if(/descending|motor/.test(group))return '#ffd46c'
 if(/gustatory|tactile/.test(group))return '#71e8ff'
 if(/visual|ol_/.test(group))return n.side==='L'?'#fb699c':'#8980ff'
 return '#6dc9f6'
}
const vertex=`attribute float neuron; attribute vec3 tint; uniform sampler2D states; uniform float width; varying vec4 state; varying vec3 hue; varying float depth;
void main(){depth=position.z;state=texture2D(states,vec2((neuron+0.5)/width,0.5));hue=tint;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);gl_PointSize=1.4;}`
const fragment=`uniform float structure; uniform float clipDepth; varying vec4 state; varying vec3 hue; varying float depth;
void main(){if(depth>clipDepth)discard;bool recorded=state.g>0.5; float strength=state.r; vec3 c=hue;float alpha;
if(structure>0.5){alpha=0.32;}else if(recorded){alpha=0.025+0.75*strength; c=mix(hue*0.3,hue,strength);}else{c=vec3(0.24,0.32,0.36);alpha=0.035;}
if(state.b>0.5){c=mix(c,vec3(1.0,0.82,0.38),0.65);alpha=max(alpha,0.62);}
gl_FragColor=vec4(c,alpha);}`
function Fibers({data,activity,scale,focus,onFocus,structure,wholeCns,angle,reset}:{data:Morphology;activity:Map<string,number>;scale:number;focus:string|null;onFocus:(id:string)=>void;structure:boolean;wholeCns:boolean;angle:BrainAngle;reset:number}){
 const {camera,controls,invalidate,size}=useThree()
 const resources=useMemo(()=>{
  const space=morphologyBounds(data,wholeCns),positions:number[]=[],tints:number[]=[],indices:number[]=[]
  data.neurons.forEach((n,index)=>{const rgb=new THREE.Color(color(n)).toArray();for(const i of n.edges){for(let a=0;a<3;a++)positions.push((n.positions[i*3+a]-space.center[a])/space.extent);tints.push(...rgb);indices.push(index)}})
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
