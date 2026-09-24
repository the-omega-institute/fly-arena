import {ReplayCamera} from './features/arena/ReplayCamera'
import {ArenaWorldLabel} from './features/arena/ArenaWorldLabel'
import {replayLabelHidden} from './features/arena/replayInspector'
import {useEffect,useMemo,useRef,useState} from 'react'
import {SceneAvailability} from './shared/SceneAvailability'
import {Canvas,useFrame,useThree} from '@react-three/fiber'
import {OrbitControls,Grid,Html} from '@react-three/drei'
import * as THREE from 'three'
import type {ArenaLayout,BodyModel,Frame,Scene,Preview} from './types'
import {useI18n} from './shared/i18n'
import {sceneThemes} from './shared/theme'
import {colors} from './types'
import {ScenePlanView} from './features/arena/ScenePlanView'
import {planDefault,planFood,planPosition} from './features/arena/sceneProjection'
import './features/arena/scenePresentation.css'
import {Habitat} from './features/arena/Habitat'
import {ArenaObstacles,arenaBounds} from './features/arena/obstacleGeometry'
import {previewSceneFraming,sceneFraming,sceneGrid,recordedCameraTarget,replayLabelOpacity} from './features/arena/followCamera'

function ReplayLabel({fly,slot,frame,next,alpha,selected,identity,follow}:{fly:Scene['flies'][number];slot:number;frame:Frame;next?:Frame;alpha:number;selected:boolean;identity?:string;follow:boolean}){
 const label=useRef<HTMLDivElement>(null),point=useMemo(()=>new THREE.Vector3(),[])
 const position=planPosition(frame,next,alpha,slot)?recordedCameraTarget(frame,next,alpha,slot):null
 useFrame(({camera,gl})=>{
  if(!label.current||!position)return
  const hud=gl.domElement.closest('.arena-stage')?.querySelector('.score-overlay')
  label.current.style.visibility=replayLabelHidden(label.current.getBoundingClientRect(),gl.domElement.getBoundingClientRect(),hud?.getBoundingClientRect())?'hidden':'visible'
  label.current.style.opacity=String(replayLabelOpacity(camera.position.distanceTo(point.set(...position)),follow))
 })
 if(!position)return null
 return <Html position={position} style={{pointerEvents:'none'}}><div ref={label} className="replay-label-anchor"><ArenaWorldLabel fly={fly} slot={slot} selected={selected} identity={identity} compact/></div></Html>
}

function AnatomicalFly({body,frame,next,alpha,color,slot=0}:{body:BodyModel;frame:Frame;next?:Frame;alpha:number;color:string;slot?:number}){
  const {resolved}=useI18n();const tokens=sceneThemes[resolved]
  const refs=useRef<(THREE.Mesh|null)[]>([])
  const geometries=useMemo(()=>Object.fromEntries(Object.entries(body.meshes).map(([key,data])=>{
    const geometry=new THREE.BufferGeometry()
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(data.vertices,3))
    geometry.setIndex(data.faces);geometry.computeVertexNormals()
    return [key,geometry]
  })),[body])
  useEffect(()=>()=>Object.values(geometries).forEach(g=>g.dispose()),[geometries])
  const quat=useMemo(()=>new THREE.Quaternion(),[])
  const nextQuat=useMemo(()=>new THREE.Quaternion(),[])
  useFrame(()=>{
    body.geoms.forEach((g,index)=>{
      if(g.slot!==slot)return
      const mesh=refs.current[index];const p=frame.poses?.[index];const n=next?.poses?.[index]||p
      if(!mesh)return
      mesh.visible=!!p&&p.length>=7&&p.every(Number.isFinite)&&!!n&&n.length>=7&&n.every(Number.isFinite)&&!(alpha>0&&next&&!next.poses?.[index])
      if(!mesh.visible)return
      mesh.position.set(p[0]+(n[0]-p[0])*alpha,p[1]+(n[1]-p[1])*alpha,p[2]+(n[2]-p[2])*alpha)
      quat.set(p[4],p[5],p[6],p[3]);nextQuat.set(n[4],n[5],n[6],n[3]);quat.slerp(nextQuat,alpha);mesh.quaternion.copy(quat)
    })
  })
  return <>{body.geoms.map((g,index)=>g.slot===slot&&<mesh key={g.id} ref={r=>{refs.current[index]=r}} geometry={geometries[g.mesh]} castShadow receiveShadow>
    <meshStandardMaterial color={g.name.includes('eye')?tokens.eye:g.name.includes('wing')?tokens.wing:color}
      transparent={g.name.includes('wing')} opacity={g.name.includes('wing')?.48:1} roughness={g.name.includes('eye')?.28:.62} metalness={.08}/>
  </mesh>)}</>
}

function RecordedTrails({frames,time,scene}:{frames:Frame[];time:number;scene:Scene}) {
  const trails=useMemo(()=>scene.flies.map((fly,slot)=>{
    const points:number[]=[],ends:number[]=[]
    frames.forEach((frame,i)=>{if(!i)return;const previous=frames[i-1],a=planPosition(previous,undefined,0,slot),b=planPosition(frame,undefined,0,slot);if(a&&b&&frame.time>previous.time){points.push(...a,.07,...b,.07);ends.push(frame.time)}})
    const geometry=new THREE.BufferGeometry().setAttribute('position',new THREE.Float32BufferAttribute(points,3))
    const line=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:colors[fly.color]||colors.mint,transparent:true,opacity:.8}))
    return {line,ends}
  }),[frames,scene])
  useEffect(()=>()=>trails.forEach(({line})=>{line.geometry.dispose();line.material.dispose()}),[trails])
  trails.forEach(({line,ends})=>{const after=ends.findIndex(end=>end>time);line.geometry.setDrawRange(0,(after<0?ends.length:after)*2)})
  return <>{trails.map(({line},i)=><primitive key={i} object={line}/>)}</>
}

function World({scene,frame}:{scene:Scene|ArenaLayout;frame?:Frame}){
  const {resolved,t}=useI18n();const tokens=sceneThemes[resolved],grid=sceneGrid(scene.size)
  const habitat=scene.habitat==='forest-floor'||('id' in scene&&scene.id==='terrarium')
  return <>
    {habitat?<Habitat size={scene.size} obstacles={scene.obstacles}/>:<>
      <mesh receiveShadow position={[0,0,-.1]}><boxGeometry args={[scene.size,scene.size,.2]}/><meshStandardMaterial color={tokens.floor} roughness={.95}/></mesh>
      <Grid args={[scene.size,scene.size]} rotation={[Math.PI/2,0,0]} position={[0,0,.012]} cellSize={grid.cell} sectionSize={grid.section} cellColor={tokens.grid} sectionColor={tokens.section} fadeDistance={grid.fade} cellThickness={.35} sectionThickness={.6}/>
    </>}
    {scene.task?.control_radius_mm&&<mesh position={[0,0,.035]}><ringGeometry args={[scene.task.control_radius_mm-.06,scene.task.control_radius_mm,96]}/><meshBasicMaterial color="#dfa576" side={THREE.DoubleSide}/></mesh>}
    {scene.task?.goal_food&&scene.food.filter(f=>f.id===scene.task?.goal_food).map(food=><Html key={food.id} position={[food.position[0],food.position[1],1.8]} center style={{pointerEvents:'none'}}><span className="spawn-label">{t('scene.goal')}</span></Html>)}
    {scene.ring_radius&&<mesh position={[0,0,.02]}><ringGeometry args={[scene.ring_radius-.09,scene.ring_radius,96]}/><meshBasicMaterial color={tokens.ring} transparent opacity={.65} side={THREE.DoubleSide}/></mesh>}
    {!habitat&&<ArenaObstacles obstacles={scene.obstacles} color={tokens.obstacle}/>}
    {scene.food.map((food,i)=>{
      const left=planFood(food,i,'flies' in scene,frame)
      return (left===null||left>.001)&&<group key={food.id} position={[food.position[0],food.position[1],food.position[2]??.12]}>
        <mesh castShadow receiveShadow><sphereGeometry args={[left===null?.45:.35+left/40,16,12]}/><meshStandardMaterial color={tokens.food} emissive={tokens.foodEmissive} emissiveIntensity={resolved==='dark'?.35:.16} roughness={.55} wireframe={left===null}/></mesh>
        <mesh position={[0,0,-.09]}><ringGeometry args={[.9,1.05,32]}/><meshBasicMaterial color={tokens.foodRing} transparent opacity={resolved==='dark'?.85:.65} side={THREE.DoubleSide}/></mesh>
      </group>
    })}
  </>
}

function ArenaScene({preview,scene,frame,next,alpha=0,color='mint',design=false,selectedId,subjectRoles,layout,participants=[],followSelected=false,frames=[]}:{frames?:Frame[];followSelected?:boolean;layout?:ArenaLayout;participants?:{name:string;color:string}[];preview?:Preview|null;scene?:Scene|null;frame?:Frame;next?:Frame;alpha?:number;color?:string;design?:boolean;selectedId?:string;subjectRoles?:Record<string,string>}){
  const {resolved}=useI18n();const tokens=sceneThemes[resolved]
  const {size:viewport}=useThree()
  const body=scene?.body||preview?.body
  const shown=frame||preview?.frame
  const world=scene||layout
  const framing=useMemo(()=>world&&layout&&!scene&&!preview?previewSceneFraming(arenaBounds(world),viewport.width/Math.max(1,viewport.height)):sceneFraming(world?arenaBounds(world):{min:[-5,-5,-.25],max:[5,5,2]},viewport.width/Math.max(1,viewport.height),design?33:40,!!world?.task),[world,layout,scene,preview,viewport.width,viewport.height,design])
  const cameraPosition:[number,number,number]=design?[6,-9,5]:framing.position
  const cameraTarget:[number,number,number]=design?[0,0,.8]:framing.target
  const span=framing.span,shadowExtent=span*.8
  return <>
    <color attach="background" args={[tokens.background]}/>
    <fog attach="fog" args={[tokens.background,framing.distance*2+span,framing.distance*3+span*3]}/>
    <hemisphereLight args={[tokens.sky,tokens.ground,1.25]}/>
    <directionalLight position={[span*.45,-span*.65,span*1.2]} color={tokens.sun} intensity={2.4} castShadow shadow-mapSize={[2048,2048]} shadow-camera-left={-shadowExtent} shadow-camera-right={shadowExtent} shadow-camera-top={shadowExtent} shadow-camera-bottom={-shadowExtent} shadow-camera-near={.1} shadow-camera-far={span*4} shadow-normalBias={.025} shadow-bias={-.0001} shadow-radius={3}/>
    <directionalLight position={[-span*.6,span*.3,span*.5]} intensity={resolved==='dark'?.8:.45} color={tokens.fill}/>
    {layout&&<>
      <World scene={layout}/>
      {layout.spawns.slice(0,participants.length).map((spawn,i)=><group key={i} position={[spawn[0],spawn[1],.08]} rotation={[0,0,spawn[2]]}>
        <mesh><ringGeometry args={[.65,.8,48]}/><meshBasicMaterial color={colors[participants[i].color]||colors.mint} side={THREE.DoubleSide}/></mesh>
        <mesh position={[1,0,0]} rotation={[0,0,-Math.PI/2]}><coneGeometry args={[.18,.55,3]}/><meshBasicMaterial color={colors[participants[i].color]||colors.mint}/></mesh>
        <Html position={[0,0,1.4]} center style={{pointerEvents:'none'}}><span className="spawn-label">{i+1} · {participants[i].name}</span></Html>
      </group>)}
    </>}
    {scene&&<World scene={scene} frame={shown}/>}
    {body&&shown&&<>
      {!scene&&<>
        <mesh position={[0,0,-.14]} rotation={[Math.PI/2,0,0]} receiveShadow><cylinderGeometry args={[4.8,5,.18,96]} /><meshStandardMaterial color={tokens.platform} roughness={.93}/></mesh>
        <Grid args={[15,15]} rotation={[Math.PI/2,0,0]} position={[0,0,-.2]} cellSize={1} sectionSize={5} cellColor={tokens.grid} sectionColor={tokens.section} fadeDistance={15} cellThickness={.35}/>
      </>}
      {scene?.flies.map((fly,i)=><ReplayLabel key={'label-'+i} fly={fly} slot={i} frame={shown} next={next} alpha={alpha} selected={fly.id===selectedId} identity={subjectRoles?.[fly.id]} follow={followSelected}/>)}
      {(scene?.flies||[{color}]).map((fly,i)=><AnatomicalFly key={i} body={body} frame={shown} next={next} alpha={alpha} slot={i} color={colors[fly.color]||colors.mint}/>)}
    </>}
    {scene&&shown&&frames.length>0&&<RecordedTrails frames={frames} time={shown.time} scene={scene}/>}
    <ReplayCamera scene={scene} frame={shown} next={next} alpha={alpha} selectedId={selectedId} follow={followSelected} overview={cameraPosition} overviewTarget={cameraTarget}/>
    <OrbitControls makeDefault enablePan={!design&&!followSelected} minDistance={design||followSelected?4:Math.max(4,span*.15)} maxDistance={design?18:framing.distance*2.5} minPolarAngle={.12} maxPolarAngle={Math.PI/2-.03}/>
    <CameraClipping far={framing.distance*4+span*4}/>
  </>
}

function CameraClipping({far}:{far:number}){
  const {camera}=useThree()
  useEffect(()=>{camera.near=.05;camera.far=far;camera.updateProjectionMatrix()},[camera,far])
  return null
}

export function ArenaCanvas(props:Parameters<typeof ArenaScene>[0]){
 const {t}=useI18n(),world=props.scene||props.layout
 const [choice,setChoice]=useState<{world:typeof world;mode:'3d'|'2d'}|null>(null)
 const mode=choice?.world===world?choice?.mode:planDefault(world)
 const fallback=<ScenePlanView world={world} recorded={!!props.scene} frame={props.frame} next={props.next} alpha={props.alpha} frames={props.frames} selectedId={props.selectedId} participants={props.participants}/>
 return <div className="scene-presentation"><SceneAvailability enabled={mode!=='2d'} fallback={fallback} controls={available=>world&&<div className="scene-presentation-toolbar" role="group" aria-label={t('scene.view')}>
  <button type="button" aria-pressed={available&&mode!=='2d'} disabled={!available} onClick={()=>setChoice({world,mode:'3d'})}>{t('scene.3d')}</button><button type="button" aria-pressed={!available||mode==='2d'} onClick={()=>setChoice({world,mode:'2d'})}>{t('scene.2d')}</button>
 </div>}>{(guard,renderer)=><Canvas shadows="soft" dpr={[1,1.7]} camera={{position:[6,-9,5],up:[0,0,1],fov:props.design?33:props.layout?52:40,near:.05,far:1000}} gl={defaults=>renderer({...defaults,antialias:true,alpha:false})} title={props.scene?t('scene.presentation'):props.layout?t('scene.layoutPresentation'):undefined}>
  {guard}<ArenaScene {...props}/>
 </Canvas>}</SceneAvailability></div>
}
