import {useEffect,useState} from 'react'
import {api} from '../../api'
import type {Fly,Identity,Match} from '../../types'
import {useI18n} from '../../shared/i18n'
import {routeHash} from '../../shared/navigation'
import './experimentSeries.css'

type Outcome={fly_id:string;score:number;outcome:'win'|'draw'|'loss'}
type Leg={seed:number;spawn_order:number;fly_ids:string[];status:string;match_ids:string[];outcomes:Outcome[]|null;issues:string[];errors:string[]}
export type Series={id:string;owner:string;created:number;spec:{name:string;fly_ids:string[];seeds:number[];map_id:string;mode:string;duration_seconds:number;bridge_profile?:string;sensory_profile?:string};status:'complete'|'running'|'incomplete';schedule:Leg[];expected_matches:number;verified_matches:number;issues:string[];unexpected_match_ids:string[];matches:Match[];standings:{fly_id:string;points:number;played:number;wins:number;draws:number;losses:number}[]}

export function ExperimentSeries({series,flies}:{series:Series;flies:Fly[]}){
 const {t}=useI18n();const name=(id:string)=>`${flies.find(f=>f.id===id)?.name||id.slice(0,8)} · ${id.slice(0,8)}`
 const replay=(id:string)=><a key={id} href={routeHash('arena','',id,series.id)}>{t(series.matches.find(m=>m.id===id)?.status==='verified'?'series.replay':'series.inspect')} · {id.slice(0,8)}</a>
 return <section className="experiment-series panel" aria-label={t('series.title')}><div className="panel-heading"><strong>{t('series.title')}</strong><span>{t('series.status.'+series.status)} · {series.verified_matches}/{series.expected_matches}</span></div><p><a href={routeHash('arena','','',series.id)}>{series.spec.name} · {series.id}</a></p><p>{series.spec.map_id} · {series.spec.mode} · {series.spec.duration_seconds} s · {series.spec.bridge_profile||'legacy-v1'} · {series.spec.sensory_profile||'odor-only-v1'}</p><p>{t('series.scope')}</p>{series.issues.map(issue=><p key={issue} role="status">{t('series.issue.'+issue)}</p>)}<div className="series-table"><table><thead><tr><th>{t('series.seed')}</th><th>{t('series.order')}</th><th>{t('series.slots')}</th><th>{t('series.status')}</th><th>{t('series.legOutcome')}</th><th>{t('series.records')}</th></tr></thead><tbody>{series.schedule.map((leg,i)=><tr key={i}><td>{leg.seed}</td><td>{leg.spawn_order}</td><td>{leg.fly_ids.map((id,slot)=><div key={id}>{slot+1} · {name(id)}</div>)}</td><td>{t('series.status.'+leg.status)}{leg.issues.map(issue=><small key={issue}>{t('series.issue.'+issue)}</small>)}{leg.errors.map((error,j)=><small key={j} role="alert">{error}</small>)}</td><td>{leg.outcomes?leg.outcomes.map(outcome=><div key={outcome.fly_id}>{name(outcome.fly_id)}: {t('series.outcome.'+outcome.outcome)} · {outcome.score}</div>):t('series.unavailable')}</td><td>{leg.match_ids.map(replay)}</td></tr>)}</tbody></table></div>{series.unexpected_match_ids.length>0&&<p>{t('series.issue.unexpected_match')}: {series.unexpected_match_ids.map(replay)}</p>}{series.status==='complete'&&series.standings.length>0?<div className="series-conclusion"><h3>{t('series.conclusion')}</h3><p>{t('series.completeScope')}</p>{series.standings.map(row=><p key={row.fly_id}><strong>{name(row.fly_id)}</strong>: {row.wins} {t('series.wins')} · {row.draws} {t('series.draws')} · {row.losses} {t('series.losses')} · {row.points} {t('series.points')}</p>)}</div>:<p>{t('series.partial')}</p>}</section>
}

export function ArenaSeries({seriesId='',identity,flies}:{seriesId?:string;identity:Identity|null;flies:Fly[]}){
 const {t}=useI18n();const [report,setReport]=useState<Series|null>(null);const [recent,setRecent]=useState<Series[]>([]);const [error,setError]=useState('');const [listError,setListError]=useState('')
 useEffect(()=>{
  setReport(null);setError('');if(!seriesId)return
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>
  async function load(){try{const result=await api<Series>('/tournaments/'+encodeURIComponent(seriesId),{signal:controller.signal});if(controller.signal.aborted)return;if(result.id!==seriesId||!Array.isArray(result.schedule))throw Error('series.invalidReport');setReport(result);setError('');if(result.status==='running'||result.schedule.some(row=>row.status==='queued'||row.status==='running'))timer=setTimeout(load,2500)}catch(e){if(!controller.signal.aborted){setReport(null);setError(e instanceof Error?e.message:String(e));timer=setTimeout(load,5000)}}}
  void load();return()=>{controller.abort();clearTimeout(timer)}
 },[seriesId])
 useEffect(()=>{
  setRecent([]);setListError('');if(!identity)return
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>
  async function load(){try{const result=await api<Series[]>('/tournaments?owner='+encodeURIComponent(identity!.id),{signal:controller.signal});if(controller.signal.aborted)return;setRecent(result.filter(item=>item.owner===identity!.id));setListError('')}catch(e){if(!controller.signal.aborted)setListError(e instanceof Error?e.message:String(e))}finally{if(!controller.signal.aborted)timer=setTimeout(load,10000)}}
  void load();return()=>{controller.abort();clearTimeout(timer)}
 },[identity?.id,seriesId])
 return <>{seriesId&&(error?<section className="panel experiment-series" role="alert">{t('series.loadError')}: {t(error)}</section>:report?.id===seriesId?<ExperimentSeries series={report} flies={flies}/>:<p role="status">{t('series.loading')}</p>)}{identity&&<section className="panel experiment-series" aria-label={t('series.recent')}><div className="panel-heading"><strong>{t('series.recent')}</strong></div>{listError&&<p role="alert">{t('series.loadError')}: {listError}</p>}{recent.map(item=><p key={item.id}><a href={routeHash('arena','','',item.id)}>{item.spec.name} · {item.id.slice(0,8)}</a> · {t('series.status.'+item.status)} · {new Date(item.created*1000).toLocaleString()}</p>)}{!recent.length&&!listError&&<p>{t('series.empty')}</p>}</section>}</>
}
