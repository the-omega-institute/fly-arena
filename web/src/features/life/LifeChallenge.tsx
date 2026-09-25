import {useEffect,useState} from 'react'
import {RefreshCw} from 'lucide-react'
import {api} from '../../api'
import type {Fly,Identity} from '../../types'
import {useI18n} from '../../shared/i18n'
import {opponentReason} from '../arena/experimentSetup'

export function LifeChallenge({fly,identity,onPrepare}:{fly:Fly;identity:Identity|null;onPrepare:(subject:Fly,opponent:Fly)=>void}){
 const {t}=useI18n();const [flies,setFlies]=useState<Fly[]>([]);const [selected,setSelected]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [revision,setRevision]=useState(0)
 useEffect(()=>{setFlies([]);setSelected('');setError('');if(!identity)return;const ctrl=new AbortController();setBusy(true);api<Fly[]>('/lives/saved',{signal:ctrl.signal},identity).then(data=>{if(!ctrl.signal.aborted)setFlies(data.filter(f=>f.owner===identity.id&&f.id!==fly.id))}).catch(e=>{if(!ctrl.signal.aborted)setError(String(e))}).finally(()=>{if(!ctrl.signal.aborted)setBusy(false)});return()=>ctrl.abort()},[fly.id,identity?.id,identity?.token,revision])
 const subject=flies.find(f=>f.id===selected),reason=subject?opponentReason(subject,fly,'legacy-v1'):undefined
 return <div className="life-challenge"><p>{t('Challenge this individual with one of your saved flies. Arena opens a paired setup; only Start submits it.')}</p>{!identity?<p>{t('Sign in and save your own fly to prepare this challenge.')}</p>:<><label>{t('Your saved challenger')}<select value={selected} disabled={busy} onChange={e=>setSelected(e.target.value)}><option value="">{t('Choose your saved fly')}</option>{flies.map(f=><option key={f.id} value={f.id}>{f.name} · {f.id.slice(0,8)}</option>)}</select></label>{busy&&<p role="status">{t('Loading saved challengers…')}</p>}{!busy&&!error&&!flies.length&&<p>{t('No saved challengers. Save a design in the workshop first.')}</p>}{error&&<p role="alert">{error}</p>}{reason&&<p role="alert">{t(reason)}</p>}<button type="button" className="life-control secondary" disabled={busy} onClick={()=>setRevision(v=>v+1)}><RefreshCw size={13}/>{t('Refresh saved challengers')}</button><button type="button" className="life-control secondary" disabled={busy||!subject||!!reason} onClick={()=>{if(subject&&!reason)onPrepare(subject,fly)}}>{t('Prepare paired challenge')}</button></>}</div>
}
