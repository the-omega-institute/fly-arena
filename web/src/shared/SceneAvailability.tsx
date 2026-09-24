import {Component,useCallback,useEffect,useRef,useState,type ReactNode} from 'react'
import {useFrame,useThree} from '@react-three/fiber'
import {WebGLRenderer,type WebGLRendererParameters} from 'three'
import {useI18n} from './i18n'
import './sceneAvailability.css'

type RendererFactory=(options:WebGLRendererParameters)=>Promise<WebGLRenderer>
type Failure='scene.webglUnavailable'|'scene.contextLost'|'scene.rendererFailed'
function webGLAvailable(){
 if(typeof document==='undefined'||typeof window==='undefined'||typeof window.WebGL2RenderingContext==='undefined')return false
 try{const gl=document.createElement('canvas').getContext('webgl2');if(!gl)return false;gl.getExtension('WEBGL_lose_context')?.loseContext();return true}catch{return false}
}
class SceneBoundary extends Component<{children:ReactNode;onFailure:()=>void},{failed:boolean}>{
 state={failed:false}
 static getDerivedStateFromError(){return {failed:true}}
 componentDidCatch(){this.props.onFailure()}
 render(){return this.state.failed?null:this.props.children}
}
function SceneRendererGuard({onLost,onFailure}:{onLost:()=>void;onFailure:()=>void}){
 const gl=useThree(s=>s.gl),failed=useRef(false)
 useEffect(()=>{
  const canvas=gl.domElement,lose=()=>{failed.current=true;onLost()},lost=(event:Event)=>{event.preventDefault();lose()}
  canvas.addEventListener('webglcontextlost',lost)
  if(gl.getContext().isContextLost())lose()
  return()=>canvas.removeEventListener('webglcontextlost',lost)
 },[gl,onLost])
 // GPU frame rendering runs outside React's error boundary. Own the render call
 // in these scenes so a renderer exception cannot leave a frozen, unlabeled view.
 useFrame(({gl,scene,camera})=>{if(failed.current)return;try{gl.render(scene,camera)}catch{failed.current=true;onFailure()}},1)
 return null
}

/** Keep data/selection/clock in the caller. Retry remounts only the GPU subtree.
 * Children must use the supplied renderer factory and place the guard inside Canvas. */
export function SceneAvailability({children,fallback,enabled=true,controls}:{children:(guard:ReactNode,renderer:RendererFactory)=>ReactNode;fallback:ReactNode;enabled?:boolean;controls?:(available:boolean)=>ReactNode}){
 const {t}=useI18n(),[failure,setFailure]=useState<Failure|null>(()=>webGLAvailable()?null:'scene.webglUnavailable'),[attempt,setAttempt]=useState(0)
 const onLost=useCallback(()=>setFailure('scene.contextLost'),[]),onFailure=useCallback(()=>setFailure('scene.rendererFailed'),[])
 const renderer=useCallback<RendererFactory>(async options=>{
  try{return new WebGLRenderer(options)}catch{
   onFailure()
   // Fiber awaits its renderer factory in configure(), outside React's boundary.
   // Suspend that failed setup until the fallback unmounts it; rejecting would
   // escape as an unhandled promise. No renderer or substitute scene is returned.
   return new Promise<WebGLRenderer>(()=>{})
  }
 },[onFailure])
 const retry=()=>{setFailure(webGLAvailable()?null:'scene.webglUnavailable');setAttempt(n=>n+1)}
 return <div className="scene-availability" data-scene-available={!failure}>
  <div className="scene-availability-content">{!failure&&enabled?<SceneBoundary key={attempt} onFailure={onFailure}>{children(<SceneRendererGuard onLost={onLost} onFailure={onFailure}/>,renderer)}</SceneBoundary>:fallback}</div>
  {failure&&<div className="scene-availability-notice"><p role="status">{t(failure)}</p><button type="button" onClick={retry}>{t('scene.retry')}</button></div>}
  {controls?.(!failure)}
 </div>
}
