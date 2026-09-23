import {Component,useCallback,useEffect,useMemo,useState,type ReactNode} from 'react'
import {Canvas,useThree} from '@react-three/fiber'
import {Html,Line,OrbitControls} from '@react-three/drei'
import {DoubleSide} from 'three'
import {Habitat} from '../arena/Habitat'
import {sceneThemes} from '../../shared/theme'
import {useI18n} from '../../shared/i18n'
import {roleStyles,type ExperimentSubject,type ProbeReport,type TrajectoryPoint} from '../../shared/research'
import {adaptProbeScene,probeFraming,probeSampleAt,type ProbeGeometry,type ProbeTrack} from './probeScene'
import './probeScene.css'

function webGLAvailable(){
 if(typeof document==='undefined'||typeof window.WebGL2RenderingContext==='undefined')return false
 try{const gl=document.createElement('canvas').getContext('webgl2');if(!gl)return false;gl.getExtension('WEBGL_lose_context')?.loseContext();return true}catch{return false}
}
class SceneBoundary extends Component<{children:ReactNode;fallback:ReactNode;onUnavailable:()=>void},{failed:boolean}>{
 state={failed:false}
 static getDerivedStateFromError(){return {failed:true}}
 componentDidCatch(){this.props.onUnavailable()}
 render(){return this.state.failed?this.props.fallback:this.props.children}
}
function ContextGuard({onUnavailable}:{onUnavailable:()=>void}){
 const gl=useThree(s=>s.gl)
 useEffect(()=>{const canvas=gl.domElement;const lost=(e:Event)=>{e.preventDefault();onUnavailable()};canvas.addEventListener('webglcontextlost',lost);return()=>canvas.removeEventListener('webglcontextlost',lost)},[gl,onUnavailable])
 return null
}
function ProbeTrail({points,time,color,dash}:{points:TrajectoryPoint[];time:number;color:string;dash:string}){
 const full=useMemo(()=>points.map(p=>[p.x,p.y,.045] as [number,number,number]),[points]);const elapsed=points.filter(p=>p.time<=time),at=probeSampleAt([points],time)
 if(at&&!elapsed.some(p=>p.time===at.time))elapsed.push(at)
 const [dashSize,gapSize]=dash?dash.split(' ').map(n=>Number(n)*.06):[0,0]
 return <>{full.length>1&&<Line points={full} color={color} lineWidth={1.5} transparent opacity={.3} dashed={!!dash} dashSize={dashSize} gapSize={gapSize}/>}{elapsed.length>1&&<Line points={elapsed.map(p=>[p.x,p.y,.05])} color={color} lineWidth={2.5} dashed={!!dash} dashSize={dashSize} gapSize={gapSize}/>}</>
}
function ProbeWorld({geometry,tracks,time}:{geometry:ProbeGeometry;tracks:ProbeTrack[];time:number}){
 const {t,resolved}=useI18n(),tokens=sceneThemes[resolved];const half=geometry.size/2
 return <>
  <Habitat size={geometry.size} obstacles={geometry.obstacles}/>
  <Line points={[[-half,-half,.04],[half,-half,.04],[half,half,.04],[-half,half,.04],[-half,-half,.04]]} color={tokens.section} lineWidth={2}/>
  {geometry.spawns.map((p,i)=><group key={i} position={[p[0],p[1],.05]} rotation={[0,0,p[2]]}><Line points={[[-.45,-.45,0],[.45,.45,0]]} color={tokens.fill}/><Line points={[[-.45,.45,0],[.45,-.45,0]]} color={tokens.fill}/><Html position={[0,-.7,0]} center className="probe-scene-label">{t('Spawn')} {i+1}</Html></group>)}
  {geometry.food.map((f,i)=><group key={i} position={f.position as [number,number,number]}><mesh><ringGeometry args={[.4,.55,32]}/><meshBasicMaterial color={tokens.food} side={DoubleSide}/></mesh><Line points={[[-.75,0,0],[.75,0,0]]} color={tokens.food}/><Line points={[[0,-.75,0],[0,.75,0]]} color={tokens.food}/><Html position={[0,1,0]} center className="probe-scene-label">{t('Food source')} · {f.id} · {t('Initial amount')}: {f.initial}</Html></group>)}
  {tracks.map(({subject,segments},i)=>{const style=roleStyles[subject.role],at=probeSampleAt(segments,time);return <group key={subject.role}>
   {segments.map((points,j)=><ProbeTrail key={j} points={points} time={time} color={style.color} dash={style.dash}/>)}
   {at&&<group position={[at.x,at.y,.06]} rotation={[0,0,at.yaw]}><mesh><ringGeometry args={[.42+i*.18,.51+i*.18,48]}/><meshBasicMaterial color={style.color} side={DoubleSide} depthTest={false}/></mesh><Line points={[[-.2,-.25,0],[.65+i*.18,0],[-.2,.25,0]]} color={style.color} lineWidth={3} depthTest={false}/><Html position={[0,0,0]} center style={{pointerEvents:'none'}}><span className="probe-scene-label" style={{color:style.color,display:'block',transform:`translateY(${24+i*20}px)`}}>{style.symbol} {subject.name}</span></Html></group>}
  </group>})}
 </>
}
export function ProbeScene3D({reports,subjects,seed,time,fallback}:{reports:ProbeReport[];subjects:ExperimentSubject[];seed:number;time:number;fallback:ReactNode}){
 const {t,resolved}=useI18n();const [mode,setMode]=useState<'3d'|'2d'>('3d');const [webgl]=useState(webGLAvailable);const [failed,setFailed]=useState(false)
 const {geometry,reason,tracks}=useMemo(()=>adaptProbeScene(reports,subjects,seed),[reports,subjects,seed]);const framing=useMemo(()=>geometry?probeFraming(geometry,tracks):null,[geometry,tracks]);const tokens=sceneThemes[resolved]
 const available=!!geometry&&webgl&&!failed,show3d=mode==='3d'&&available;const unavailable=useCallback(()=>setFailed(true),[])
 return <div className="probe-scene">
  <div className="probe-scene-toolbar" role="group" aria-label={t('Probe view')}><button type="button" aria-pressed={show3d} disabled={!available} onClick={()=>setMode('3d')}>{t('3D')}</button><button type="button" aria-pressed={!show3d} onClick={()=>setMode('2d')}>{t('2D plan')}</button></div>
  {reason&&<p className="plot-note" role="status">{t(reason==='conflict'?'Probe geometry conflicts between reports; 3D unavailable.':'Recorded probe geometry unavailable; showing the 2D plan.')}</p>}
  {!reason&&(!webgl||failed)&&<p className="plot-note" role="status">{t('WebGL unavailable; showing the 2D plan.')}</p>}
  {show3d&&geometry&&framing?<><p className="plot-note">{t('Recorded planar trajectories · tokens show x/y/yaw only; positions and heading interpolate between samples. No body pose, gait or altitude is recorded.')}</p><p className="plot-note">{t('Drag to orbit, scroll to zoom. Food markers show initial sources, not remaining food or cue activity. Ground and lighting are illustrative.')}</p><div className="probe-scene-viewport" role="region" aria-label={t('3D recorded probe scene')}>
   <SceneBoundary key={seed} onUnavailable={unavailable} fallback={fallback}><Canvas shadows dpr={[1,1.7]} camera={{position:framing.position,up:[0,0,1],fov:43,near:.01,far:framing.span*15}} gl={{antialias:true,alpha:true}} fallback={fallback}>
    <ContextGuard onUnavailable={unavailable}/><ambientLight intensity={.8}/><hemisphereLight args={[tokens.sky,tokens.ground,1.6]}/><directionalLight position={[framing.span*.4,-framing.span*.5,framing.span]} intensity={3.2} castShadow shadow-mapSize={[1024,1024]} shadow-camera-left={-framing.span} shadow-camera-right={framing.span} shadow-camera-top={framing.span} shadow-camera-bottom={-framing.span} shadow-camera-far={framing.span*4} shadow-bias={-.0003}/><directionalLight position={[-framing.span*.5,framing.span*.4,framing.span*.3]} intensity={1.5} color={tokens.fill}/>
    <ProbeWorld geometry={geometry} tracks={tracks} time={time}/><OrbitControls makeDefault target={framing.target} minDistance={1} maxDistance={framing.span*6} minPolarAngle={.05} maxPolarAngle={Math.PI/2-.03}/>
   </Canvas></SceneBoundary>
  </div></>:fallback}
  <div className="probe-scene-status">{tracks.map(track=><span key={track.subject.role}>{roleStyles[track.subject.role].symbol} {track.subject.name} · {t(track.status)}{track.invalid?' · '+t('Invalid trajectory samples omitted'):''}{!probeSampleAt(track.segments,time)?' · '+t('No recorded position at shared time'):''}</span>)}</div>
 </div>
}
