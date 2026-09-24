import {ArrowRight} from 'lucide-react'
import type {ArenaMap,Fly,Match,Season} from '../../types'
import {useI18n} from '../../shared/i18n'
import {baselineComparison,guideComparisonPlan} from '../guide/nextAction'
import type {ExperimentPlan} from '../arena/experimentSetup'

type Props={fly?:Fly;flies:Fly[];maps:ArenaMap[];season:Season|null;matches:Match[];budget:number;needed:number;duration:number;onCompare:(plan:ExperimentPlan)=>void;onReplay:(match:Match)=>void;onConfigure:()=>void;disabled?:boolean}
export function FirstExperimentGuide({fly,flies,maps,season,matches,budget,needed,duration,onCompare,onReplay,onConfigure,disabled=false}:Props){
 const {t}=useI18n(),plan=guideComparisonPlan(flies,fly?.id||'',maps,season),comparison=baselineComparison(flies,fly,matches)
 const count=(value:number)=>Number.isFinite(value)&&Number.isInteger(value)&&value>0?value:'—'
 return <section className="panel first-experiment-guide" aria-label={t('training.first.title')}>
  <h2>{t('training.first.title')}</h2><p>{fly?<><strong>{fly.name}</strong> · {t('training.first.saved')}</>:t('training.first.choose')}</p>
  <div className="training-pair"><div><h3>{t('training.first.compare')}</h3><p>{t(comparison?'training.first.recorded':'training.first.baseline')}</p>
   <button className="secondary" disabled={disabled||(!comparison&&!plan)} onClick={()=>{if(comparison)onReplay(comparison[0]);else if(plan)onCompare(plan)}}>{t(comparison?'training.first.inspect':'training.first.prepare')}<ArrowRight size={14}/></button>
   {!comparison&&!plan&&<p role="status">{t('training.first.unavailable')}</p>}
  </div><div><h3>{t('training.first.optimize')}</h3><p>{t('training.first.search')}</p><button className="secondary" disabled={disabled||!fly} onClick={onConfigure}>{t('training.first.configure')}<ArrowRight size={14}/></button></div></div>
  <p>{t('training.first.budget')} <strong>{count(budget)}</strong> · {t('training.first.planned')} <strong>{count(needed)}</strong> × {count(duration)} s</p>
  <p>{t('training.first.budgetMeaning')}</p><p>{t('training.first.results')}</p>
 </section>
}
