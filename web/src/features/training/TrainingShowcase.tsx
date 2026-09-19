import {lifeHash} from '../life/navigation'
import {useEffect,useState} from 'react'
import {ArrowRight,Download,GitBranch} from 'lucide-react'
import {api} from '../../api'
import type {ArenaMap,Fly,Match} from '../../types'
import {useI18n} from '../../shared/i18n'
import {TrainingComparison} from './TrainingComparison'
import {summarizeRun,type ComparableRun} from './comparison'
import {ConditionResults} from './ConditionResults'
import type {ConditionResult} from './ConditionResults'
import {algorithmName} from './algorithms'
import './training.css'
export type PublishedRun=Omit<ComparableRun,'members'> & {best_fly_id:string;members:{generation:number;slot:number;fitness:number;fly_id:string;fly:Fly;matches:Match[];condition_results:ConditionResult[]}[]}
export function TrainingShowcase({maps,onReplay,onBranch,copyAvailable=false,busy=false,revision=0}:{maps:ArenaMap[];onReplay:(m:Match)=>void;onBranch:(fly:Fly,spec:ComparableRun['spec'],runId:string)=>void;copyAvailable?:boolean;busy?:boolean;revision?:number}){
 const {t}=useI18n();const [runs,setRuns]=useState<PublishedRun[]>([]);const [selected,setSelected]=useState(()=>new URLSearchParams(typeof location==='undefined'?'':location.hash.slice(1)).get('showcase')||'');const [generation,setGeneration]=useState(0);const [error,setError]=useState('');const [loading,setLoading]=useState(true)
 useEffect(()=>{const c=new AbortController();setLoading(true);api<PublishedRun[]>('/training-showcase',{signal:c.signal}).then(data=>{setRuns(data);setError('')}).catch(e=>{if(!c.signal.aborted)setError(String(e))}).finally(()=>{if(!c.signal.aborted)setLoading(false)});return()=>c.abort()},[revision])
 useEffect(()=>{const sync=()=>{setSelected(new URLSearchParams(location.hash.slice(1)).get('showcase')||'');setGeneration(0)};window.addEventListener('hashchange',sync);window.addEventListener('popstate',sync);return()=>{window.removeEventListener('hashchange',sync);window.removeEventListener('popstate',sync)}},[])
 function selectRun(id:string){setSelected(id);setGeneration(0);const params=new URLSearchParams(location.hash.slice(1));params.set('tab','train');params.set('showcase',id);history.replaceState(null,'','#'+params.toString())}
 const current=runs.find(r=>r.id===selected)||runs[0]
 const round=current?summarizeRun(current).history[generation]:null
 function download(run:PublishedRun){const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([JSON.stringify(run,null,2)],{type:'application/json'}));link.download='evolution-'+run.id+'.json';link.click();URL.revokeObjectURL(link.href)}
 return <section className="evolution-showcase panel" aria-label={t('Evolution gallery')}>
  <div className="showcase-heading"><div><span className="tiny-label">EVOLUTION / OPEN NOTEBOOK</span><h2>{t('Watch algorithms design a fly.')}</h2><p>{t('Real evaluations, recorded generations, inspectable brains. Explore an example, then start your own branch.')}</p></div><GitBranch size={32}/></div>
  <p className="training-hint">{t('Short demonstrations show the optimization loop, not biological equivalence or proof that one algorithm is better. Flat or worse scores are kept.')}</p>
  {loading&&<p role="status">{t('Loading evolution examples…')}</p>}{error&&<p role="alert">{error}</p>}
  {!loading&&!error&&!runs.length&&<p>{t('No published examples yet. Complete a session and publish its trajectory to share it here.')}</p>}
  {!!runs.length&&!copyAvailable&&<p className="training-hint">{t('This server offers read-only examples. Saving a copy is not available yet.')}</p>}
  {!!runs.length&&<>
   <TrainingComparison runs={runs} maps={maps} flies={runs.flatMap(r=>r.members.map(m=>m.fly))} onOpen={selectRun} initiallyOpen/>
   <div className="training-tabs">{runs.map(r=><button key={r.id} className={current?.id===r.id?'active':''} onClick={()=>selectRun(r.id)}>{r.spec.name}<small>{t(algorithmName(r.spec.strategy))}</small></button>)}</div>
   {current&&<>
    <div className="showcase-actions"><strong>{current.spec.name}</strong><button className="secondary" onClick={()=>download(current)}><Download size={14}/>{t('Export results and lineage')}</button></div>
    <div className="generation-list">{Array.from({length:current.spec.generations},(_,g)=><button key={g} className={generation===g?'active':''} onClick={()=>setGeneration(g)}><span>{current.spec.strategy==='random_search'?'R':'G'}{g+1}</span><small>{current.members.filter(m=>m.generation===g).length} {t('evaluated')}</small></button>)}</div>
    <p className="training-hint">{t('Round best')}: {round?.best?.toFixed(4)??'—'} · {t('Historical best')}: {round?.bestSoFar?.toFixed(4)??'—'}</p>
    <div className="showcase-individuals">{current.members.filter(m=>m.generation===generation).map(m=><article key={m.fly_id} className="training-individual">
      <span className="tiny-label">{current.spec.strategy==='random_search'?'R':'G'}{m.generation+1} · {m.slot+1}{m.fly_id===current.best_fly_id?' · '+t('Best so far'):''}</span><h3>{m.fly.name}</h3><a className="text-link" href={lifeHash(m.fly_id)}>{t('Open life record')}</a>
      <div className="individual-score"><span>{t('Candidate fitness')}</span><strong>{m.fitness.toFixed(3)}</strong></div>
      <p>{t('Parent')} · {m.fly.spec.parent_id?.slice(0,8)} · {t('Mutation budget')} {m.fly.report.budget_used.toFixed(2)}</p>
      <div className="individual-genes">{m.fly.spec.weight_mutations.length?m.fly.spec.weight_mutations.map(w=><span key={w.selector}>{t(w.selector)} ×{w.scale.toFixed(3)}</span>):<span>{t('Baseline')}</span>}</div>
      <ConditionResults results={m.condition_results} maps={maps} onReplay={onReplay}/>
      <button className="secondary" disabled={!copyAvailable||busy} onClick={()=>onBranch(m.fly,current.spec,current.id)}>{t('Save a copy and prepare training')}<ArrowRight size={14}/></button>
    </article>)}</div>
   </>}
  </>}
 </section>
}
