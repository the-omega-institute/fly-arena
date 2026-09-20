import {useI18n} from '../../shared/i18n'
import {evaluationCount} from './plan'

type Props={population:number;generations:number;mode:'forage'|'contest';conditions:{map_id:string;seed:number}[];duration:number}

export function TrainingWorkload(props:Props){
 const {locale}=useI18n(),zh=locale==='zh-CN'
 const evaluations=evaluationCount(props),flies=props.mode==='contest'?2:1
 const seconds=evaluations*props.duration
 const valid=[props.population,props.generations,props.duration].every(n=>Number.isInteger(n)&&n>0)
 const count=(n:number)=>valid?n.toLocaleString(locale):'—'
 return <section className="training-workload" aria-label={zh?'训练工作量':'Training workload'} aria-live="polite">
  <dl>
   <div><dt>{zh?'每场仿真':'Per evaluation'}</dt><dd>{count(props.duration)} s · {flies} {zh?'只果蝇':'flies'}</dd></div>
   <div><dt>{zh?'计划总仿真时长':'Planned simulation time'}</dt><dd>{count(seconds)} s</dd></div>
   <div><dt>{zh?'所有大脑累计仿真时长':'Simulation time across all brains'}</dt><dd>{count(seconds*flies)} s</dd></div>
  </dl>
  <p>{zh?'双体评估包含双方大脑；交换出生位置已计入评估次数。以上是模拟时间，实际等待取决于模型、硬件与队列，不是完成倒计时。':'Both brains run in a contest; swapped positions already count as separate evaluations. These are simulated seconds. Actual waiting depends on model, hardware and queue, not a completion countdown.'}</p>
  <p>{props.duration<=2
   ?zh?'当前 1–2 秒窗口适合试通提交和回放，果蝇可能还来不及接近食物。评估觅食可选择 5–30 秒，并检查身体与脑活动。':'The current 1–2 s window is useful for trying submission and replay; the fly may not have time to reach food. For feeding evaluation, choose 5–30 s and inspect body and brain activity.'
   :zh?'较长窗口可以观察接触后的行为；单个窗口的高分仍需与 WT 对照，并在未参与训练的条件下评估。':'A longer window can reveal behavior after contact. Compare high scores with WT and evaluate under conditions not used for training.'}</p>
 </section>
}
