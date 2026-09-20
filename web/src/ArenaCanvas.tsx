import {ReplayCamera} from './features/arena/ReplayCamera'
import {ArenaWorldLabel} from './features/arena/ArenaWorldLabel'
import {useEffect,useMemo,useRef} from 'react'
import {Canvas,useFrame} from '@react-three/fiber'
import {OrbitControls,Grid,Html} from '@react-three/drei'
import * as THREE from 'three'
import type {ArenaLayout,BodyModel,Frame,Scene,Preview} from './types'
import {useI18n} from './shared/i18n'
import {sceneThemes} from './shared/theme'
import {colors} from './types'
import {Habitat} from './features/arena/Habitat'

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
      const mesh=refs.current[index];const p=frame.poses[index];const n=next?.poses[index]||p
      if(!mesh||!p)return
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
  const geometry=useMemo(()=>scene.flies.map((_,slot)=>{
    const g=new THREE.BufferGeometry()
    g.setAttribute('position',new THREE.Float32BufferAttribute(frames.flatMap(f=>[f.positions[slot][0],f.positions[slot][1],.07]),3))
    return g
  }),[frames,scene])
  useEffect(()=>()=>geometry.forEach(g=>g.dispose()),[geometry])
  const count=Math.max(1,frames.findIndex(f=>f.time>time))
  geometry.forEach(g=>g.setDrawRange(0,time>=frames[frames.length-1].time?frames.length:count))
  const lines=useMemo(()=>geometry.map((g,i)=>new THREE.Line(g,new THREE.LineBasicMaterial({color:colors[scene.flies[i].color]||colors.mint,transparent:true,opacity:.65}))),[geometry,scene])
  useEffect(()=>()=>lines.forEach(line=>line.material.dispose()),[lines])
  return <>{lines.map((line,i)=><primitive key={i} object={line}/>)}</>
}

function World({scene,frame}:{scene:Scene|ArenaLayout;frame?:Frame}){
  const {resolved,locale}=useI18n();const tokens=sceneThemes[resolved]
  const habitat=scene.habitat==='forest-floor'||('id' in scene&&scene.id==='terrarium')
  return <>
    {habitat?<Habitat size={scene.size} obstacles={scene.obstacles}/>:<>
      <mesh receiveShadow position={[0,0,-.1]}><boxGeometry args={[scene.size,scene.size,.2]}/><meshStandardMaterial color={tokens.floor} roughness={.95}/></mesh>
      <Grid args={[scene.size,scene.size]} rotation={[Math.PI/2,0,0]} position={[0,0,.012]} cellSize={1} sectionSize={5} cellColor={tokens.grid} sectionColor={tokens.section} fadeDistance={65} cellThickness={.35} sectionThickness={.6}/>
    </>}
    {scene.task?.control_radius_mm&&<mesh position={[0,0,.035]}><ringGeometry args={[scene.task.control_radius_mm-.06,scene.task.control_radius_mm,96]}/><meshBasicMaterial color="#dfa576" side={THREE.DoubleSide}/></mesh>}
    {scene.task?.goal_food&&scene.food.filter(f=>f.id===scene.task?.goal_food).map(food=><Html key={food.id} position={[food.position[0],food.position[1],1.8]} center style={{pointerEvents:'none'}}><span className="spawn-label">{locale==='zh-CN'?'终点 / 实际接触':'GOAL / physical contact'}</span></Html>)}
    {scene.ring_radius&&<mesh position={[0,0,.02]}><ringGeometry args={[scene.ring_radius-.09,scene.ring_radius,96]}/><meshBasicMaterial color={tokens.ring} transparent opacity={.65} side={THREE.DoubleSide}/></mesh>}
    {!habitat&&scene.obstacles.map((o,i)=><mesh key={i} position={o.position as [number,number,number]} castShadow receiveShadow><boxGeometry args={o.size as [number,number,number]}/><meshStandardMaterial color={tokens.obstacle} roughness={.8}/></mesh>)}
    {scene.food.map((food,i)=>{
      const left=frame?.food?.[i]??food.initial
      return left>.001&&<group key={food.id} position={[food.position[0],food.position[1],food.position[2]??.12]}>
        <mesh castShadow receiveShadow><sphereGeometry args={[.35+left/40,16,12]}/><meshStandardMaterial color={habitat?'#bd7440':tokens.food} emissive={habitat?'#572919':tokens.foodEmissive} emissiveIntensity={habitat?.1:.18} roughness={habitat?.52:.4}/></mesh>
        <mesh position={[0,0,-.09]}><ringGeometry args={[.9,1.05,32]}/><meshBasicMaterial color={tokens.foodRing} transparent opacity={.3} side={THREE.DoubleSide}/></mesh>
      </group>
    })}
  </>
}

export function ArenaCanvas({preview,scene,frame,next,alpha=0,color='mint',design=false,selectedId,subjectRoles,layout,participants=[],followSelected=false,frames=[]}:{frames?:Frame[];followSelected?:boolean;layout?:ArenaLayout;participants?:{name:string;color:string}[];preview?:Preview|null;scene?:Scene|null;frame?:Frame;next?:Frame;alpha?:number;color?:string;design?:boolean;selectedId?:string;subjectRoles?:Record<string,string>}){
  const {resolved,t}=useI18n();const tokens=sceneThemes[resolved]
  const body=scene?.body||preview?.body
  const shown=frame||preview?.frame
  const habitat=scene?.habitat==='forest-floor'||layout?.habitat==='forest-floor'||layout?.id==='terrarium'
  const cameraPosition:( [number,number,number])=design?[6,-9,5]:(scene?.task||layout?.task)?[16,-22,32]:habitat?[17,-25,12]:[22,-28,26]
  return <Canvas shadows dpr={[1,1.7]} camera={{position:cameraPosition,up:[0,0,1],fov:design?33:habitat?43:40,near:.05,far:250}} gl={{antialias:true,alpha:true}}>
    <ambientLight intensity={habitat?.65:.8}/><hemisphereLight args={[habitat?'#dbe8d0':tokens.sky,habitat?'#4b4034':tokens.ground,habitat?1.9:1.6]}/>
    <directionalLight position={habitat?[7,-10,18]:[6,-5,12]} intensity={habitat?3.8:3.2} castShadow shadow-mapSize={[2048,2048]} shadow-camera-left={-25} shadow-camera-right={25} shadow-camera-top={25} shadow-camera-bottom={-25} shadow-bias={-.0003}/>
    <directionalLight position={[-7,5,3]} intensity={habitat?1.9:1.5} color={habitat?'#d9b98a':tokens.fill}/>
    {habitat&&<pointLight position={[-5,4,7]} intensity={1.2} distance={35} color="#b6d29c"/>}
    {layout&&<>
      <World scene={layout}/>
      {layout.spawns.slice(0,participants.length).map((spawn,i)=><group key={i} position={[spawn[0],spawn[1],.08]} rotation={[0,0,spawn[2]]}>
        <mesh><ringGeometry args={[.65,.8,48]}/><meshBasicMaterial color={colors[participants[i].color]||colors.mint} side={THREE.DoubleSide}/></mesh>
        <mesh position={[1,0,0]} rotation={[0,0,-Math.PI/2]}><coneGeometry args={[.18,.55,3]}/><meshBasicMaterial color={colors[participants[i].color]||colors.mint}/></mesh>
        <Html position={[0,0,1.4]} center style={{pointerEvents:'none'}}><span className="spawn-label">{i+1} · {participants[i].name}</span></Html>
      </group>)}
    </>}
    {body&&shown&&<>
      {scene?<World scene={scene} frame={shown}/>:<>
        <mesh position={[0,0,-.14]} rotation={[Math.PI/2,0,0]} receiveShadow><cylinderGeometry args={[4.8,5,.18,96]} /><meshStandardMaterial color={tokens.platform} roughness={.93}/></mesh>
        <Grid args={[15,15]} rotation={[Math.PI/2,0,0]} position={[0,0,-.2]} cellSize={1} sectionSize={5} cellColor={tokens.grid} sectionColor={tokens.section} fadeDistance={15} cellThickness={.35}/>
      </>}
      {scene?.flies.map((fly,i)=>{const p=shown.positions?.[i],n=next?.positions?.[i]||p;if(!p)return null;return <Html key={'label-'+i} position={[p[0]+(n[0]-p[0])*alpha,p[1]+(n[1]-p[1])*alpha,(p[2]||0)+(scene.task?(i===0?2.2:3.8):1.6)]} center style={{pointerEvents:'none'}}><ArenaWorldLabel fly={fly} slot={i} selected={fly.id===selectedId} identity={subjectRoles?.[fly.id]} compact={!!scene.task}/></Html>})}
      {(scene?.flies||[{color}]).map((fly,i)=><AnatomicalFly key={i} body={body} frame={shown} next={next} alpha={alpha} slot={i} color={colors[fly.color]||colors.mint}/>)}
    </>}
    {scene?.task&&shown&&frames.length>0&&<RecordedTrails frames={frames} time={shown.time} scene={scene}/>}
    {scene&&shown&&<ReplayCamera scene={scene} frame={shown} next={next} alpha={alpha} selectedId={selectedId} follow={followSelected} overview={cameraPosition}/>}
    <OrbitControls makeDefault target={design?[0,0,.8]:habitat?[0,0,.25]:[0,0,0]} enablePan={!design&&!followSelected} minDistance={design||followSelected?4:habitat?7:10} maxDistance={design?18:75} minPolarAngle={.12} maxPolarAngle={Math.PI/2-.03}/>
  </Canvas>
}
