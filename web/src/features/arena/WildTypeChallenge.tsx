import {ArrowRight,Leaf} from 'lucide-react'
import type {Fly} from '../../types'
import {useI18n} from '../../shared/i18n'
import {wildTypeChallenge} from './wildtype'

export function WildTypeChallenge({flies,selected,onPrepare}:{flies:Fly[];selected:string;onPrepare:(plan:NonNullable<ReturnType<typeof wildTypeChallenge>>)=>void}) {
  const {locale}=useI18n();const zh=locale==='zh-CN'
  const plan=wildTypeChallenge(flies,selected)
  return <section className="wt-challenge" aria-label={zh?'WT 对照挑战':'WT comparison challenge'}>
    <div><Leaf size={18}/><strong>{zh?'从一个公平的对照开始':'Start with a fair comparison'}</strong></div>
    <p>{zh?'WT 是未修改的模拟基线。与它比赛，观察你的设计改变了什么。':'WT is the unmodified simulated baseline. Compete against it to see what your design changes.'}</p>
    {plan?<p className="wt-participants"><b>{plan.subject.name}</b> vs <b>{plan.reference.name}</b></p>:<p>{zh?'先在下方选择一只与 WT 不同的已保存果蝇；对照需要相同图谱与神经模型。':'Choose a different saved fly below. The WT reference must use the same connectome and neural model.'}</p>}
    <button className="secondary wide" disabled={!plan} onClick={()=>{if(plan)onPrepare(plan)}}><Leaf size={15}/>{zh?'准备挑战 WT':'Prepare WT challenge'}<ArrowRight size={15}/></button>
    <small>{zh?'预设：果园 · seed 42 · 每场 2 秒。准备后点击“双循环系列赛”运行换边两场，共 4 模拟秒。':'Preset: orchard · seed 42 · 2 seconds per match. Then start the two-match series to swap positions: 4 simulated seconds total.'}</small>
  </section>
}
