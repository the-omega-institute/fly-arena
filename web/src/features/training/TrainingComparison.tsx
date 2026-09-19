import {algorithmName} from './algorithms'
import {useState} from 'react'
import {ArrowRight,Download,GitCompareArrows} from 'lucide-react'
import type {ArenaMap,Fly} from '../../types'
import {useI18n} from '../../shared/i18n'
import {comparisonDifferences,curveScale,summarizeRun,evaluationConditions} from './comparison'
import type {ComparableRun} from './comparison'

const colors=['#538b76','#bc7253','#8572ac']
const score=(n:number|null)=>n===null?'—':n.toFixed(3)

export function TrainingComparison({runs,maps,flies,onOpen,initiallyOpen=false}:{runs:ComparableRun[];maps:ArenaMap[];flies:Fly[];onOpen:(id:string)=>void;initiallyOpen?:boolean}){
  const {t,locale}=useI18n()
  const [chosen,setChosen]=useState<string[]|null>(null)
  const ids=chosen??runs.slice(0,3).map(r=>r.id)
  const selected=runs.filter(r=>ids.includes(r.id))
  const differences=comparisonDifferences(selected)
  const scale=curveScale(selected)
  const rows=selected.map(run=>({run,...summarizeRun(run)}))
  const name=(id:string|null)=>flies.find(f=>f.id===id)?.name||id?.slice(0,8)||'—'
  function exportComparison(){
    const data={sessions:rows.map(({run,...summary})=>({id:run.id,status:run.status,spec:run.spec,
      evaluation_context:run.evaluation_context,...summary,evaluations_started:run.evaluations_started,
      evaluations_completed:run.evaluations_completed,evaluations_planned:run.evaluations_total})),
      differing_conditions:differences,interpretation:'Descriptive training-condition results; no held-out generalization claim. Time budget is completed evaluations times configured duration, not actual runtime.'}
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}))
    const link=document.createElement('a');link.href=url;link.download='training-comparison.json';link.click();URL.revokeObjectURL(url)
  }
  return <details className="panel training-comparison" open={initiallyOpen||undefined}>
    <summary><GitCompareArrows size={17}/><span>{t('Compare training strategies')}</span><small>{t('Up to three sessions')}</small></summary>
    <div className="comparison-content">
      <p>{t('Compare real generation scores and evaluation costs. This view starts no simulations.')}</p>
      {!runs.length?<p>{t('Your training sessions will appear here.')}</p>:<>
        <div className="comparison-select">{runs.map(run=><label key={run.id}><input type="checkbox" checked={ids.includes(run.id)} disabled={!ids.includes(run.id)&&selected.length>=3} onChange={e=>setChosen(e.target.checked?[...selected.map(r=>r.id),run.id]:selected.filter(r=>r.id!==run.id).map(r=>r.id))}/><span>{run.spec.name}<small>{run.id.slice(0,8)}</small></span></label>)}</div>
        {selected.length<2?<p role="status">{t('Select at least two sessions to compare.')}</p>:<p className={'comparison-note '+(differences.length?'conditions-differ':'')} role="status">{differences.length?<>{t('Different evaluation conditions:')} {differences.map(key=>t(key)).join(' · ')}. {t('Read these as separate experiments.')}</>:t('Same recorded evaluation conditions. These are training results, not held-out generalization evidence.')}</p>}
        {rows.length>0&&<>
          <div className="comparison-legend">{rows.map(({run},i)=><span key={run.id} style={{color:colors[i]}}>● {run.spec.name}</span>)}</div>
          <svg className="comparison-chart" viewBox="0 0 700 220" role="img" aria-label={t('Round best and historical best')}>
            {[scale.min,0,scale.max].map((value,i)=><g key={i}><line x1="60" x2="655" y1={scale.y(value)} y2={scale.y(value)} stroke="currentColor" opacity=".15"/><text x="48" y={scale.y(value)+4} textAnchor="end">{value.toFixed(2)}</text></g>)}
            {Array.from({length:Math.max(...selected.map(r=>r.spec.generations))},(_,generation)=><text key={generation} x={scale.x(generation)} y="202" textAnchor="middle">R{generation+1}</text>)}
            {rows.map(({run,history},i)=><g key={run.id}>{history.map((point,index)=>{
              if(point.best===null)return null
              const prev=history[index-1]
              return <g key={index}>
                {prev?.bestSoFar!=null&&point.bestSoFar!=null&&<line x1={scale.x(prev.generation)} y1={scale.y(prev.bestSoFar)} x2={scale.x(index)} y2={scale.y(point.bestSoFar)} stroke={colors[i]} opacity=".65" strokeWidth="2" strokeDasharray="5 5"/>}
                {prev?.best!=null&&<line x1={scale.x(prev.generation)} y1={scale.y(prev.best)} x2={scale.x(index)} y2={scale.y(point.best)} stroke={colors[i]} strokeWidth="2" opacity={point.complete&&prev.complete?1:.5}/>}
                <circle cx={scale.x(index)} cy={scale.y(point.best)} r="4" fill={point.complete?colors[i]:'var(--paper)'} stroke={colors[i]} strokeWidth="2"><title>{`${run.spec.name} · R${index+1} · ${score(point.best)} · ${point.evaluated}/${run.spec.population}`}</title></circle>
              </g>
            })}</g>)}
          </svg>
          <p>{t('Solid: round best. Dashed: historical best. A worse candidate does not erase earlier results.')}</p><p>{t('Round best and historical best')} · {t('Hollow points indicate partially evaluated generations. Missing results remain blank.')}</p>
          <div className="comparison-table-wrap"><table className="comparison-table"><thead><tr><th>{t('Session name')}</th><th>{t('Starting fitness')}</th><th>{t('Best fitness')}</th><th>{t('Change from baseline')}</th><th>{t('Evaluations completed')}</th><th>{t('Evaluated time budget')}</th></tr></thead><tbody>{rows.map(({run,baseline,best,gain,budgetedSeconds},i)=><tr key={run.id}>
            <td><button className="text-link" style={{color:colors[i]}} onClick={()=>onOpen(run.id)}>{run.spec.name}<ArrowRight size={13}/></button><small>{t(algorithmName(run.spec.strategy))}</small><small>{run.status==='complete'?t('Complete'):t('Incomplete session')}</small></td>
            <td>{score(baseline)}</td><td>{score(best)}</td><td>{gain===null?'—':(gain>0?'+':'')+score(gain)}</td><td>{run.evaluations_completed} / {run.evaluations_total}<small>{t('Started')} {run.evaluations_started} · {t('Limit')} {run.spec.max_evaluations}</small></td><td>{budgetedSeconds} s</td>
          </tr>)}</tbody></table></div>
          <p>{t('Time budget is completed evaluations × configured duration, not wall time or hardware cost. Best score includes the baseline.')}</p>
          <div className="comparison-conditions">{rows.map(({run},i)=><article key={run.id}><strong style={{color:colors[i]}}>{run.spec.name}</strong><dl>
            <div><dt>{t('Selection objective')}</dt><dd>{t(run.spec.fitness_objective==='sustained-foraging-v1'?'Sustained foraging':'Food collected')}</dd></div>
            <div><dt>{t('Sensory profile')}</dt><dd>{run.spec.sensory_profile||'odor-only-v1'}</dd></div>
            <div><dt>{t('Brain model')}</dt><dd>{run.model_profile||'malecns-lif-cpu-v1'}</dd></div>
            <div><dt>{t('Starting fly')}</dt><dd>{name(run.spec.founder_id)}</dd></div>
            <div><dt>{t('Evaluation conditions')}</dt>{evaluationConditions(run.spec).map((c,i)=><dd key={i}>{maps.find(m=>m.id===c.map_id)?.[locale==='en'?'english':'name']||c.map_id} · {t('Seed')} {c.seed}</dd>)}</div>
            <div><dt>{t('Objective')}</dt><dd>{t(run.spec.mode==='contest'?'Compete for food':'Collect food')}</dd></div>
            {run.spec.mode==='contest'&&<div><dt>{t('Fixed opponent')}</dt><dd>{name(run.spec.opponent_id)}</dd></div>}
            <div><dt>{t('Seed')}</dt><dd>{run.spec.seed} · {run.spec.duration_seconds} s</dd></div>
            <div><dt>{t('Population')}</dt><dd>{run.spec.population} × {run.spec.generations} {t(run.spec.strategy==='random_search'?'Search rounds':'Generations')}</dd></div>
            <div><dt>{t('Allow mutations in')}</dt><dd>{run.spec.strategy==='external'?t('Your own optimizer · API'):run.spec.circuits.map(c=>t(c)).join(', ')}</dd></div>
            {run.spec.strategy!=='external'&&<div><dt>{t('Mutation strength')}</dt><dd>{Math.round(run.spec.mutation_strength*100)}%</dd></div>}
          </dl></article>)}</div>
          <button className="secondary" onClick={exportComparison}><Download size={14}/>{t('Export comparison')}</button>
        </>}
      </>}
    </div>
  </details>
}
