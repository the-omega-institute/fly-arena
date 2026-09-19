import type {ArenaMap,Match} from '../../types'
import {useI18n} from '../../shared/i18n'
import {evaluationConditions} from './comparison'
import {algorithmName} from './algorithms'
import type {PublishedRun} from './TrainingShowcase'

const multimodal=new Set(['engineered-multimodal-v1','engineered-multimodal-v2','engineered-touch-response-v1'])
const separated=new Set(['engineered-contact-context-v1','engineered-contact-support-v1'])

export function ExperimentGuide({run,maps,onReplay}:{run:PublishedRun;maps:ArenaMap[];onReplay:(match:Match)=>void}){
 const {locale,t}=useI18n(),zh=locale==='zh-CN'
 const best=run.members.find(m=>m.fly_id===run.best_fly_id)
 const baseline=run.members.find(m=>m.generation===0&&m.slot===0)
 const playable=(member:typeof best)=>member?.matches.find(m=>m.status==='verified'&&m.request.fly_ids.includes(member.fly_id))
 const bestMatch=playable(best),baselineMatch=playable(baseline)
 const sensory=run.spec.sensory_profile
 const inputs=sensory==='odor-only-v1'?(zh?'嗅觉进入大脑；视觉和触觉仅作环境观察。':'Odor enters the brain; vision and touch are environment observations only.'):
  sensory&&separated.has(sensory)?(zh?'嗅觉、工程化视觉、味觉和左右触觉输入大脑。':'Odor, engineered vision, taste and left/right touch enter the brain.'):
  sensory&&multimodal.has(sensory)?(zh?'嗅觉、工程化视觉和接触电流输入大脑。':'Odor, engineered vision and contact currents enter the brain.'):
  (zh?'感觉输入说明不可用，请在回放中检查记录的输入配置。':'Input description unavailable; inspect the recorded sensory configuration in the replay.')
 const bridge=run.spec.bridge_profile==='sensorimotor-research-v2'?(zh?'核函数读出与运动变换':'Kernel readout and motor transfer'):
  run.spec.bridge_profile==='legacy-v1'?(zh?'线性读出与滤波驱动':'Linear readout and filtered drive'):
  run.spec.bridge_profile||(zh?'未记录':'Not recorded')
 const model=run.model_profile||best?.fly.spec.model_profile||(zh?'未记录':'Not recorded')
 return <section className="experiment-guide" aria-label={zh?'本次演化怎么观察':'How to observe this experiment'}>
  <div className="experiment-guide-heading"><div><span className="tiny-label">DESIGN → BODY → BRAIN</span>
   <h3>{zh?'先看它怎么生活，再看分数如何变化':'Watch its behavior, then explore the scores'}</h3>
   <p>{zh?'打开一个个体的回放，选择接触或摄取事件，暂停查看身体和同步脑图，再展开神经元与修改过的连接。':'Open an individual’s replay, choose a contact or intake event, pause to inspect its body and synchronized brain, then explore neurons and edited connections.'}</p>
  </div><div className="experiment-guide-actions">
   <button className="primary" disabled={!bestMatch} onClick={()=>bestMatch&&onReplay(bestMatch)}>{zh?'观看最佳个体':'Watch best individual'} →</button>
   <button className="secondary" disabled={!baselineMatch} onClick={()=>baselineMatch&&onReplay(baselineMatch)}>{zh?'观看实验基线':'Watch experiment baseline'} →</button>
  </div></div>
  <dl className="experiment-guide-facts">
   <div><dt>{zh?'演化算法':'Evolution algorithm'}</dt><dd>{t(algorithmName(run.spec.strategy))}</dd></div>
   <div><dt>{zh?'大脑模型':'Brain model'}</dt><dd>{model}</dd></div>
   <div><dt>{zh?'感觉—运动方案':'Sensorimotor setup'}</dt><dd>{bridge}</dd></div>
   <div><dt>{zh?'训练条件':'Training conditions'}</dt><dd>{evaluationConditions(run.spec).map((c,i)=><span key={i}>{maps.find(m=>m.id===c.map_id)?.[zh?'name':'english']||c.map_id} · seed {c.seed} · {run.spec.duration_seconds} s</span>)}</dd></div>
  </dl>
  <p className="experiment-guide-inputs">{inputs} <small>{sensory||(zh?'输入配置未记录':'Sensory profile not recorded')}</small></p>
  <p className="training-hint">{zh?'真实连接组约束大脑结构；感觉编码、神经动力学和身体控制是仿真假设。脑图亮度来自已记录活动，灰色或未采样节点不表示零活动。':'The real connectome constrains brain structure; sensory encoding, neural dynamics and body control are simulation assumptions. Brain brightness comes from recorded activity; gray or unsampled nodes do not mean zero activity.'}</p>
  <p className="training-hint">{zh?'这些回放来自训练条件。最佳个体可能仍是基线；多条件实验的快捷入口打开第一份已完成回放，可在下方选择其余条件。基线是实验起点，不自动等于 WT。':'These replays use training conditions. The best individual may still be the baseline. For multiple conditions, shortcuts open the first completed replay; select other conditions below. The baseline is the experiment’s starting point, not automatically WT.'}</p>
 </section>
}
