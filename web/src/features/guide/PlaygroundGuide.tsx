import {useEffect, useState} from 'react'
import {ArrowRight, Bot, BookOpen, ChevronDown, ChevronUp, ExternalLink} from 'lucide-react'
import {useI18n} from '../../shared/i18n'
import {guideSections,journeySteps,nextGuideStep} from './content'
import type {GuideAction,GuideMessageKey} from './content'
import './guide.css'

export type PlaygroundGuideProps = {
  onDesign:()=>void
  onTrain:()=>void
  onArena:()=>void
  onAI:()=>void
  onCloneWT:()=>void
  canCloneWT:boolean
  hasSavedDesign:boolean
  onCompare:()=>void
  canCompare:boolean
  hasCompared?:boolean
  hasEvolved?:boolean
  subjectName?:string
  evidenceError?:string
  neuronCount?:number
}

const STORAGE_KEY='flyarena.playground-guide-collapsed'

export function PlaygroundGuide({onDesign,onTrain,onArena,onAI,onCloneWT,canCloneWT,hasSavedDesign,neuronCount,onCompare,canCompare,hasCompared=false,hasEvolved=false,subjectName,evidenceError}:PlaygroundGuideProps){
  const {t,locale}=useI18n()
  const [expanded,setExpanded]=useState(true)
  const actions:Record<GuideAction,()=>void>={clone:onCloneWT,design:onDesign,compare:onCompare,train:onTrain,compete:onArena}

  useEffect(()=>{
    try{if(window.localStorage.getItem(STORAGE_KEY)==='1')setExpanded(false)}catch{}
  },[])

  const next=nextGuideStep({hasSavedDesign,hasCompared,hasEvolved})
  const disabled=(action:GuideAction)=>action==='clone'?!canCloneWT:action==='compare'?!canCompare:false
  const nextAction=<button className="playground-guide__action" data-guide-next={next.id} disabled={disabled(next.action!)} onClick={actions[next.action!]}>{t(next.title)}<ArrowRight size={14}/></button>

  const collapse=()=>{setExpanded(false);try{window.localStorage.setItem(STORAGE_KEY,'1')}catch{}}
  const reopen=()=>{setExpanded(true);try{window.localStorage.removeItem(STORAGE_KEY)}catch{}}
  const learnMore=(title:GuideMessageKey)=><summary aria-label={t('guide.learnMore')+': '+t(title)}>{t('guide.learnMore')}<ChevronDown size={14}/></summary>

  if(!expanded)return <section className="playground-guide playground-guide--collapsed" aria-label={t('guide.label')}><BookOpen size={17}/><span>{t('guide.next')}</span>{nextAction}<button className="playground-guide__reopen" onClick={reopen} aria-label={t('guide.reopen')}><ChevronDown size={16}/></button></section>

  return <section className="playground-guide" aria-labelledby="playground-guide-title">
    <div className="playground-guide__topline"><span className="playground-guide__eyebrow"><span/> {t('guide.eyebrow')}</span><button className="playground-guide__collapse" onClick={collapse} aria-label={t('guide.collapse')}><ChevronUp size={16}/></button></div>
    <div className="playground-guide__intro"><div><h2 id="playground-guide-title">{t('guide.next')}: {t(next.title)}</h2><p>{t(next.summary)}{subjectName&&<> · <strong>{subjectName}</strong></>}</p>{nextAction}<p>{t('guide.prepareOnly')}</p>{next.id==='clone'&&!canCloneWT&&<p role="status">{t('guide.noWT')}</p>}{next.id==='compare'&&!canCompare&&<p role="status">{t('guide.noComparison')}</p>}{evidenceError&&<p role="status">{t('guide.evidenceError')} {evidenceError}</p>}</div>{neuronCount!==undefined&&<div className="playground-guide__count"><strong>{neuronCount.toLocaleString(locale)}</strong><span>{t('guide.count')}</span></div>}</div>
    <ol className="playground-guide__sections">
      {guideSections.map((section,index)=><li key={section.id} className="playground-guide__section" data-guide-section={section.id}>
        <span className="playground-guide__number" aria-hidden="true">{String(index+1).padStart(2,'0')}</span>
        <div className="playground-guide__section-content"><details className="playground-guide__details"><summary aria-label={t('guide.learnMore')+': '+t(section.title)}><h3>{t(section.title)}</h3><ChevronDown size={14}/></summary><p>{t(section.summary)}</p><div className="playground-guide__detail-copy">{section.details.map(key=><p key={key}>{t(key)}</p>)}</div>
            {section.links&&<div className="playground-guide__sources">{section.links.map(link=><a key={link.href} href={link.href} target="_blank" rel="noreferrer">{t(link.label)}<ExternalLink size={12}/></a>)}</div>}
          {section.id==='journey'&&<ol className="playground-guide__steps" aria-label={t(section.title)}>{journeySteps.map((step,index)=><li key={step.id} className="playground-guide__step" data-guide-step={step.id}>
            <span aria-hidden="true">{index+1}</span><div><h4>{t(step.title)}</h4><p>{t(step.summary)}</p><details className="playground-guide__details">{learnMore(step.title)}<p>{t(step.detail)}</p></details></div>
            {step.action&&step.label&&<button className="playground-guide__action" onClick={actions[step.action]} disabled={disabled(step.action)}>{t(step.action==='design'&&hasSavedDesign?'guide.action.edit':step.label)}<ArrowRight size={14}/></button>}
          </li>)}</ol>}
          {section.id==='meaning'&&<button className="playground-guide__action" onClick={onAI}><Bot size={14}/>{t('guide.action.ai')}<ArrowRight size={14}/></button>}
          </details>
        </div>
      </li>)}
    </ol>
  </section>
}
