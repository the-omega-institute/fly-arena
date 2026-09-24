import {useEffect,useState} from 'react'
import {Loader2} from 'lucide-react'
import {api} from '../../api'
import {ArenaCanvas} from '../../ArenaCanvas'
import type {Fly} from '../../types'
import {useI18n} from '../../shared/i18n'
import {mapPurpose} from './mapPurpose'
import type {MapPreviewLayout} from './mapPurpose'

export function MapPurposeLegend({layout}:{layout:MapPreviewLayout}){
  const {t}=useI18n(),legend=mapPurpose(layout,t),unknown=t('Unavailable')
  return <section aria-label={t('Map purpose and suitability')} style={{padding:'10px 14px',fontSize:11,lineHeight:1.6,borderTop:'1px solid var(--border)',background:'var(--surface)',maxHeight:'48%',overflowY:'auto',flexShrink:0}}>
    <div style={{display:'flex',gap:8,alignItems:'baseline',flexWrap:'wrap'}}><strong>{t('Map purpose and suitability')}</strong><span data-scientific-status={layout.metadata?.scientific_status||'unavailable'} style={{border:'1px solid var(--border)',borderRadius:12,padding:'0 7px'}}>{legend.status}</span></div>
    <p>{legend.purpose}</p>
    <div style={{display:'flex',flexWrap:'wrap',gap:'2px 12px'}}><span>{t('Spawn slots')}: {legend.spawnSlots??unknown}</span><span>{t('Food patches')}: {legend.foodCount??unknown}</span><span>{t('Solid obstacles')}: {legend.obstacleCount??unknown}</span><span>{t('Arena size')}: {legend.sizeMm===null?unknown:`${legend.sizeMm} × ${legend.sizeMm} mm`}</span></div>
    <p>{t('Supported map modes')}: {legend.modes.length?legend.modes.join(' · '):unknown}</p>
    {legend.horizon&&<p>{t('Suggested observation horizon')}: {legend.horizon} {t('simulated seconds')}</p>}
    <p>{t('Limitation')}: {legend.limitation}</p>
    <small style={{color:'var(--text-muted)'}}>{t('Modeled seeded layout, not a recorded run. Horizon guidance is exploratory; profile readiness and run limits apply separately.')}</small>
  </section>
}

export function MapPreview({mapId,seed,bridgeProfile,participants}:{mapId:string;seed:number;bridgeProfile:string;participants:(Fly|undefined)[]}) {
  const {t}=useI18n()
  const key=`${mapId}:${seed}:${bridgeProfile}`
  const [loaded,setLoaded]=useState<{key:string;layout:MapPreviewLayout}|null>(null)
  const [failure,setFailure]=useState<{key:string;message:string}|null>(null)
  useEffect(()=>{
    const controller=new AbortController()
    api<MapPreviewLayout>(`/maps/${encodeURIComponent(mapId)}/preview?seed=${seed}&bridge_profile=${encodeURIComponent(bridgeProfile||'legacy-v1')}`,{signal:controller.signal})
      .then(layout=>{if(!controller.signal.aborted){setLoaded({key,layout});setFailure(null)}})
      .catch(error=>{if(!controller.signal.aborted)setFailure({key,message:error.message})})
    return()=>controller.abort()
  },[key,mapId,seed,bridgeProfile])
  if(failure?.key===key)return <div className="canvas-loading" role="status">{t('Map preview unavailable')}<small>{failure.message}</small></div>
  if(loaded?.key!==key)return <div className="canvas-loading" role="status"><Loader2 className="spin"/>{t('Loading map…')}</div>
  return <div style={{height:'100%',display:'flex',flexDirection:'column'}}><div style={{flex:1,minHeight:0}}><ArenaCanvas key={key} layout={loaded.layout} participants={participants.map((fly,i)=>({name:fly?.name||t(i===0?'Your fly':'Opponent'),color:fly?.color||(i===0?'mint':'violet')}))}/></div><MapPurposeLegend layout={loaded.layout}/></div>
}
