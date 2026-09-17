import {useEffect,useState} from 'react'
import {Loader2} from 'lucide-react'
import {api} from '../../api'
import {ArenaCanvas} from '../../ArenaCanvas'
import type {ArenaLayout,Fly} from '../../types'
import {useI18n} from '../../shared/i18n'

export function MapPreview({mapId,seed,bridgeProfile,participants}:{mapId:string;seed:number;bridgeProfile:string;participants:(Fly|undefined)[]}) {
  const {t}=useI18n()
  const key=`${mapId}:${seed}:${bridgeProfile}`
  const [loaded,setLoaded]=useState<{key:string;layout:ArenaLayout}|null>(null)
  const [failure,setFailure]=useState<{key:string;message:string}|null>(null)
  useEffect(()=>{
    const controller=new AbortController()
    api<ArenaLayout>(`/maps/${encodeURIComponent(mapId)}/preview?seed=${seed}&bridge_profile=${encodeURIComponent(bridgeProfile||'legacy-v1')}`,{signal:controller.signal})
      .then(layout=>{if(!controller.signal.aborted){setLoaded({key,layout});setFailure(null)}})
      .catch(error=>{if(!controller.signal.aborted)setFailure({key,message:error.message})})
    return()=>controller.abort()
  },[key,mapId,seed,bridgeProfile])
  if(failure?.key===key)return <div className="canvas-loading" role="status">{t('Map preview unavailable')}<small>{failure.message}</small></div>
  if(loaded?.key!==key)return <div className="canvas-loading" role="status"><Loader2 className="spin"/>{t('Loading map…')}</div>
  return <ArenaCanvas layout={loaded.layout} participants={participants.map((fly,i)=>({name:fly?.name||t(i===0?'Your fly':'Opponent'),color:fly?.color||(i===0?'mint':'violet')}))}/>
}
