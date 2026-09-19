import {useEffect,useMemo,useState} from 'react'
import type {ReplayEvent} from '../../types'
import {useI18n} from '../../shared/i18n'
import {lifeEvents,lifeEventPage,lifeEventPageAtTime,type LifeEventKind} from './lifeEvents'

export function LifeEventTimeline({events,slot,time,onSelect,label}:{events:ReplayEvent[];slot:number;time:number;onSelect:(event:ReplayEvent)=>void;label:(event:ReplayEvent)=>string}) {
  const {t,locale}=useI18n()
  const [kind,setKind]=useState<LifeEventKind>('all'),[page,setPage]=useState(0)
  useEffect(()=>setPage(0),[events,slot,kind])
  const filtered=useMemo(()=>lifeEvents(events,slot,kind),[events,slot,kind])
  const shown=lifeEventPage(filtered,page)
  const next=filtered.findIndex(event=>event.tick/10000>time)
  const lastObserved=filtered[(next===-1?filtered.length:next)-1]
  return <div className="event-timeline life-event-navigation">
    <div className="life-event-toolbar"><strong>{t('Life events')}</strong>
      <select aria-label={t('Filter life events')} value={kind} onChange={event=>{setKind(event.target.value as LifeEventKind);setPage(0)}}>
        <option value="all">{t('All events')}</option><option value="food">{t('Food and sensing')}</option>
        <option value="contact">{t('Body contact')}</option><option value="outcome">{t('Boundary exit')}</option>
      </select>
      <button disabled={!filtered.length} onClick={()=>setPage(lifeEventPageAtTime(filtered,time))}>{t('Locate playhead')}</button>
    </div>
    <div className="life-event-rows">{shown.rows.map((event,index)=><button key={`${shown.start+index}:${event.tick}:${event.type}`} aria-current={event===lastObserved?'step':undefined} onClick={()=>onSelect(event)}>
      <span>{(event.tick*.0001).toFixed(2)}s</span>{label(event)}{event.objects?.length?' · '+event.objects.join(', '):''}
    </button>)}</div>
    {!filtered.length?<small>{t('No events in this category.')}</small>:<div className="life-event-pager">
      <button aria-label={t('Earlier events')} disabled={shown.page===0} onClick={()=>setPage(shown.page-1)}>← {t('Earlier events')}</button>
      <span aria-live="polite">{shown.start+1}–{shown.start+shown.rows.length} / {filtered.length}</span>
      <button aria-label={t('Later events')} disabled={shown.page===shown.pages-1} onClick={()=>setPage(shown.page+1)}>{t('Later events')} →</button>
    </div>}
    <small className="life-event-help">{locale==='zh-CN'?'点击事件，查看其后的首个实际采样及脑活动；所有事件都可翻页查阅。':'Select an event to inspect the first recorded sample after it and its brain activity. Every event remains available across pages.'}</small>
  </div>
}
