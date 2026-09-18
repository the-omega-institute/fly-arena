import {useEffect, useState} from 'react'
import type {ReactNode} from 'react'
import {ArrowRight, Bot, BookOpen, ChevronDown, ChevronUp, ExternalLink, GitBranch, FlaskConical, Play, Sparkles} from 'lucide-react'
import {useI18n} from '../../shared/i18n'
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
  const {locale}=useI18n()
  const zh=locale==='zh-CN'
  const [expanded,setExpanded]=useState(true)

  useEffect(()=>{
    try{if(window.localStorage.getItem(STORAGE_KEY)==='1')setExpanded(false)}catch{}
  },[])

  const collapse=()=>{setExpanded(false);try{window.localStorage.setItem(STORAGE_KEY,'1')}catch{}}
  const reopen=()=>{setExpanded(true);try{window.localStorage.removeItem(STORAGE_KEY)}catch{}}
  const copy=(en:string,cn:string)=>zh?cn:en
  const action=(label:string,cn:string,icon:ReactNode,onClick:()=>void,disabled=false)=><button className="playground-guide__action" onClick={onClick} disabled={disabled}>{icon}<span>{copy(label,cn)}</span><ArrowRight size={14}/></button>

  if(!expanded)return <section className="playground-guide playground-guide--collapsed" aria-label={copy('Playground guide','实验场指南')}><BookOpen size={17}/><span>{copy('New here? Start with the guide','第一次来？从指南开始')}</span><button className="playground-guide__reopen" onClick={reopen} aria-label={copy('Reopen playground guide','重新打开实验场指南')}><ChevronDown size={16}/></button></section>

  return <section className="playground-guide" aria-labelledby="playground-guide-title">
    <div className="playground-guide__topline"><span className="playground-guide__eyebrow"><span/> {copy('FIELD GUIDE / FIRST STEPS','实验场指南 / 第一步')}</span><button className="playground-guide__collapse" onClick={collapse} aria-label={copy('Collapse playground guide','收起实验场指南')}><ChevronUp size={16}/></button></div>
    <div className="playground-guide__intro">
      <div><h2 id="playground-guide-title">{copy('Meet your first digital fly.','认识你的第一只数字果蝇。')}</h2><p>{copy('Start from the unmodified Wild Type (WT), make one small design change, then train and compare it under the same arena rules.','从未修改的野生型（WT）开始，做一个小改动，再在相同竞技规则下训练和比较。')}</p></div>
      {neuronCount!==undefined&&<div className="playground-guide__count"><strong>{neuronCount.toLocaleString()}</strong><span>{copy('pinned neurons in this graph','图谱中的固定神经元')}</span></div>}
    </div>
    <div className="playground-guide__steps" aria-label={copy('Suggested first steps','建议的第一步')}>
      <div className="playground-guide__step"><span>01</span><div><strong>{copy('Clone WT','复制 WT')}</strong><p>{copy('A clean simulated baseline to compare against.','一个干净的模拟基线，用来做比较。')}</p></div>{action('Use WT','使用 WT',<GitBranch size={14}/>,onCloneWT,!canCloneWT)}</div>
      <div className="playground-guide__step"><span>02</span><div><strong>{copy('Edit and save one circuit','编辑并保存一个回路')}</strong><p>{copy('Change a weight or neuron parameter, then save the design within the budget.','修改一个权重或神经元参数，再在预算内保存设计。')}</p></div>{action(hasSavedDesign?'Edit and save':'Open design',hasSavedDesign?'编辑并保存':'打开设计',<FlaskConical size={14}/>,onDesign)}</div>
      <div className="playground-guide__step"><span>03</span><div><strong>{copy('Train and test','训练并测试')}</strong><p>{copy('Use finite evaluations, then inspect the recorded result.','使用有限次评测，再检查记录下来的结果。')}</p></div><div className="playground-guide__mini-actions"><button onClick={onTrain}><Play size={13}/>{copy('Train','训练')}</button><button onClick={onArena}><ArrowRight size={13}/>{copy('Compare','比较')}</button></div></div>
    </div>
    <div className="playground-guide__ai"><div className="playground-guide__ai-icon"><Sparkles size={18}/></div><div><strong>{copy('Bring an AI co-designer','让 AI 成为共同设计者')}</strong><p>{copy('An AI agent can propose the same FlySpec edits and submit them for the same validation and arena evaluation.','AI agent 可以提出相同格式的 FlySpec 修改，并经过同样的验证和竞技场评测。')}</p></div><button onClick={onAI}>{copy('Connect an AI','接入 AI')}<Bot size={15}/></button></div>
    <details className="playground-guide__science">
      <summary><span><BookOpen size={16}/>{copy('How this fly works','这只果蝇如何工作')}</span><ChevronDown size={16}/></summary>
      <div className="playground-guide__pipeline"><div><b>01</b><strong>{copy('Real connectome source','真实图谱来源')}</strong><p>{copy('The pinned MaleCNS v1.0 connectome supplies the graph structure. EM images are reconstructed into neurons and synapse partners; this is not a live animal.','固定的 MaleCNS v1.0 神经图谱提供网络结构。电子显微镜图像被重建为神经元和突触配对；它不是活体动物。')}</p><a href="https://male-cns.janelia.org/" target="_blank" rel="noreferrer">{copy('MaleCNS source','MaleCNS 来源')} <ExternalLink size={12}/></a></div><ArrowRight size={15}/><div><b>02</b><strong>{copy('Simulated neuron dynamics','模拟神经元动力学')}</strong><p>{copy('The retained graph runs with a simplified current based leaky integrate and fire (LIF) model. Structural synapse counts are not experimentally known physiological weights.','保留的图谱使用简化的电流驱动漏积分发放（LIF）模型运行。结构突触数量不等于实验测得的生理权重。')}</p></div><ArrowRight size={15}/><div><b>03</b><strong>{copy('Sensory to motor bridge','感觉到运动的连接')}</strong><p>{copy('This alpha primarily uses engineered odor/current input and a low level gait readout. It has two bilateral locomotion action channels.','当前版本主要使用工程化气味/电流输入和低层步态读出，仅有两个双侧运动动作通道。')}</p></div><ArrowRight size={15}/><div><b>04</b><strong>{copy('Body and records','身体与记录')}</strong><p>{copy('FlyGym/NeuroMechFly body behavior is stepped in MuJoCo. Runs record neural traces, motion, events, scores and replay evidence.','FlyGym/NeuroMechFly 身体行为在 MuJoCo 中推进。运行会记录神经曲线、运动、事件、分数和回放证据。')}</p><a href="https://github.com/NeLy-EPFL/flygym" target="_blank" rel="noreferrer">{copy('FlyGym source','FlyGym 来源')} <ExternalLink size={12}/></a></div></div>
      <p className="playground-guide__boundary">{copy('WT is the unmodified simulated baseline. The model is not identical to a real animal: vision, online learning and memory tasks are not enabled, and the low level gait is engineered rather than learned.','WT 是未修改的模拟基线。该模型不等同于真实动物：当前未启用视觉、在线学习和记忆任务，低层步态也是工程化的，而不是学习得到的。')}</p>
    </details>
  </section>
}
