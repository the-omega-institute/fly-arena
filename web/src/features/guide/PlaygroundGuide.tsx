import {useEffect, useState} from 'react'
import {ArrowRight, Bot, BookOpen, ChevronDown, ChevronUp, ExternalLink} from 'lucide-react'
import {useI18n} from '../../shared/i18n'
import {guideSections,journeySteps} from './content'
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
  neuronCount?:number
}

const STORAGE_KEY='flyarena.playground-guide-collapsed'

export function PlaygroundGuide({onDesign,onTrain,onArena,onAI,onCloneWT,canCloneWT,hasSavedDesign,neuronCount}:PlaygroundGuideProps){
  const {t,locale}=useI18n()
  const [expanded,setExpanded]=useState(true)
  const actions:Record<GuideAction,()=>void>={clone:onCloneWT,design:onDesign,compare:onArena,train:onTrain,compete:onArena}

  useEffect(()=>{
    try{if(window.localStorage.getItem(STORAGE_KEY)==='1')setExpanded(false)}catch{}
  },[])

  const collapse=()=>{setExpanded(false);try{window.localStorage.setItem(STORAGE_KEY,'1')}catch{}}
  const reopen=()=>{setExpanded(true);try{window.localStorage.removeItem(STORAGE_KEY)}catch{}}
  const learnMore=(title:GuideMessageKey)=><summary aria-label={t('guide.learnMore')+': '+t(title)}>{t('guide.learnMore')}<ChevronDown size={14}/></summary>

  if(!expanded)return <section className="playground-guide playground-guide--collapsed" aria-label={t('guide.label')}><BookOpen size={17}/><span>{t('guide.reopenPrompt')}</span><button className="playground-guide__reopen" onClick={reopen} aria-label={t('guide.reopen')}><ChevronDown size={16}/></button></section>

  return <section className="playground-guide" aria-labelledby="playground-guide-title">
    <div className="playground-guide__topline"><span className="playground-guide__eyebrow"><span/> {t('guide.eyebrow')}</span><button className="playground-guide__collapse" onClick={collapse} aria-label={t('guide.collapse')}><ChevronUp size={16}/></button></div>
    <div className="playground-guide__intro"><div><h2 id="playground-guide-title">{t('guide.title')}</h2><p>{t('guide.intro')}</p></div>{neuronCount!==undefined&&<div className="playground-guide__count"><strong>{neuronCount.toLocaleString(locale)}</strong><span>{t('guide.count')}</span></div>}</div>
    <ol className="playground-guide__sections">
      {guideSections.map((section,index)=><li key={section.id} className="playground-guide__section" data-guide-section={section.id}>
        <span className="playground-guide__number" aria-hidden="true">{String(index+1).padStart(2,'0')}</span>
        <div className="playground-guide__section-content"><h3>{t(section.title)}</h3><p>{t(section.summary)}</p>
          <details className="playground-guide__details">{learnMore(section.title)}<div className="playground-guide__detail-copy">{section.details.map(key=><p key={key}>{t(key)}</p>)}</div>
            {section.links&&<div className="playground-guide__sources">{section.links.map(link=><a key={link.href} href={link.href} target="_blank" rel="noreferrer">{t(link.label)}<ExternalLink size={12}/></a>)}</div>}
          </details>
          {section.id==='journey'&&<ol className="playground-guide__steps" aria-label={t(section.title)}>{journeySteps.map((step,index)=><li key={step.id} className="playground-guide__step" data-guide-step={step.id}>
            <span aria-hidden="true">{index+1}</span><div><h4>{t(step.title)}</h4><p>{t(step.summary)}</p><details className="playground-guide__details">{learnMore(step.title)}<p>{t(step.detail)}</p></details></div>
            {step.action&&step.label&&<button className="playground-guide__action" onClick={actions[step.action]} disabled={step.action==='clone'&&!canCloneWT}>{t(step.action==='design'&&hasSavedDesign?'guide.action.edit':step.label)}<ArrowRight size={14}/></button>}
          </li>)}</ol>}
          {section.id==='meaning'&&<button className="playground-guide__action" onClick={onAI}><Bot size={14}/>{t('guide.action.ai')}<ArrowRight size={14}/></button>}
        </div>
      </li>)}
    </ol>
  </section>
}
