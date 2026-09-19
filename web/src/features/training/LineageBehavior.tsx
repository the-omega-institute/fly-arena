import {useState} from 'react'
import type {Match} from '../../types'
import {useI18n} from '../../shared/i18n'
import type {PublishedRun} from './TrainingShowcase'

type Member=PublishedRun['members'][number]

// Keep spawn position and every other participant fixed. A swapped contest is
// a different comparison, even if its map and seed are identical.
export function matchedLifeReplay(member:Member,target:Member,reference:Match):Match|undefined{
 const key=(match:Match,id:string)=>{
  const r=match.request
  if(!r.fly_ids.includes(id))return null
  return JSON.stringify([r.map_id,r.mode,r.seed,r.duration_seconds,r.bridge_profile||'legacy-v1',
   r.sensory_profile||'odor-only-v1',r.fly_ids.map(f=>f===id?'candidate':f)])
 }
 if(member.fly.spec.connectome_sha256!==target.fly.spec.connectome_sha256||member.fly.spec.model_profile!==target.fly.spec.model_profile)return undefined
 const expected=key(reference,target.fly_id)
 return expected?member.matches.find(m=>m.status==='verified'&&key(m,member.fly_id)===expected):undefined
}

export function LineageBehavior({run,onReplay}:{run:PublishedRun;onReplay:(match:Match)=>void}){
 const {locale,t}=useI18n(),zh=locale==='zh-CN'
 const [chosen,setChosen]=useState(run.best_fly_id)
 const [matchId,setMatchId]=useState('')
 const candidate=run.members.find(m=>m.fly_id===chosen)||run.members.find(m=>m.fly_id===run.best_fly_id)||run.members[0]
 if(!candidate)return null
 const matches=candidate.matches.filter(m=>m.status==='verified'&&m.request.fly_ids.includes(candidate.fly_id))
 const reference=matches.find(m=>m.id===matchId)||matches[0]
 const baseline=run.members.find(m=>m.generation===0&&m.slot===0)
 const parent=run.members.find(m=>m.fly_id===candidate.fly.spec.parent_id)
 const rows:{label:string;member:Member|undefined}[]=[
  {label:zh?'本次实验基线':'Experiment baseline',member:baseline},
  {label:zh?'记录中的亲代':'Recorded parent',member:parent},
  {label:zh?'选中的后代':'Selected candidate',member:candidate},
 ]
 const number=(n:number|undefined)=>n!==undefined&&Number.isFinite(n)?n.toFixed(3):'—'
 return <section className="lineage-behavior" aria-label={zh?'亲代与后代的行为对照':'Parent and offspring behavior'}>
  <div className="lineage-behavior-heading"><div><span className="tiny-label">BODY / BRAIN / LINEAGE</span><h3>{zh?'分数之外，后代改变了什么？':'What changed in the offspring’s behavior?'}</h3>
   <p>{zh?'选择一个后代，查看同条件的基线和亲代，再打开身体与大脑回放。':'Choose a candidate, inspect its baseline and parent under matching conditions, then open the body and brain replays.'}</p></div>
   <label>{zh?'观察个体':'Observe individual'}<select value={candidate.fly_id} onChange={e=>{setChosen(e.target.value);setMatchId('')}}>{run.members.map(m=><option key={m.fly_id} value={m.fly_id}>G{m.generation+1}.{m.slot+1} · {m.fly.name}</option>)}</select></label>
  </div>
  {reference?<>
   <label className="lineage-condition">{zh?'对照场景与出生位':'Comparison scene and spawn position'}<select value={reference.id} onChange={e=>setMatchId(e.target.value)}>{matches.map(m=><option key={m.id} value={m.id}>{m.request.map_id} · seed {m.request.seed} · {m.request.duration_seconds}s · {zh?'出生位':'slot'} {m.request.fly_ids.indexOf(candidate.fly_id)+1}</option>)}</select></label>
   <div className="comparison-table-wrap"><table className="comparison-table lineage-behavior-table"><thead><tr>
    {[zh?'生命记录':'Life record',zh?'总摄取':'Total food',zh?'后半程摄取':'Second-half food',zh?'未倒置时间':'Time not inverted',zh?'首次倒置':'First inversion',zh?'身体与脑活动':'Body and brain'].map(label=><th key={label}>{label}</th>)}
   </tr></thead><tbody>{rows.map(({label,member})=>{
    const match=member?matchedLifeReplay(member,candidate,reference):undefined
    const slot=match&&member?match.request.fly_ids.indexOf(member.fly_id):-1
    const metric=match?.result?.behavior?.[slot]
    const measured=metric?.schema==='sustained-foraging-v1'?metric:undefined
    return <tr key={label}><td><strong>{label}</strong><small>{member?`G${member.generation+1}.${member.slot+1} · ${member.fly.name}`:(zh?'此实验未收录亲代评估':'Parent evaluation not included in this experiment')}</small></td>
     <td>{number(measured?.food)}</td><td>{number(measured?.latter_half_food)}</td><td>{measured?`${(measured.upright_fraction*100).toFixed(1)}%`:'—'}</td>
     <td>{measured?(measured.first_inversion_s===null?(zh?'窗口内未记录':'None recorded in window'):`${measured.first_inversion_s.toFixed(2)} s`):'—'}</td>
     <td>{match?<button className="text-link" onClick={()=>onReplay(match)}>{zh?'观看身体与大脑':'Watch body and brain'} →</button>:<small>{zh?'无同条件回放':'No matching replay'}</small>}</td></tr>
   })}</tbody></table></div>
   <p className="training-hint">{zh?'只配对相同地图、种子、时长、感觉配置、模型与出生位的记录；对手也保持相同。— 表示未记录，不是零。基线是本次实验的起点，不自动等同于野生型。':'Replays are paired by map, seed, duration, sensory configuration, model and spawn position, with the same opponent. — means unrecorded, not zero. The experiment baseline is not automatically wild type.'}</p>
  </>:<p>{zh?'这个个体尚无已完成的行为回放。':'This individual has no completed behavior replay yet.'}</p>}
  <details className="lineage-design"><summary>{zh?'查看三者的大脑设计':'Inspect their brain designs'}</summary><div className="lineage-design-grid">{rows.map(({label,member})=><article key={label}><strong>{label}</strong>{member?<>
   <p>{member.fly.spec.weight_mutations.length?member.fly.spec.weight_mutations.map((w,i)=><span key={i}>{t(w.selector)} ×{w.scale.toFixed(3)}</span>):<span>{zh?'无回路权重倍率修改':'No circuit multiplier changes'}</span>}</p>
   <small>τ ×{member.fly.spec.neuron_parameters.tau_scale} · {zh?'阈值偏移':'Threshold shift'} {member.fly.spec.neuron_parameters.threshold_shift_mv} mV</small>
   <small>{zh?'逐边修改':'Edge changes'}: {member.fly.spec.edge_deltas.length} · {zh?'可塑性':'Plasticity'}: {member.fly.spec.plasticity}</small>
  </>:<p>—</p>}</article>)}</div><p className="training-hint">{zh?'这里展示提交的倍率与神经参数。重叠回路、逐边修改及其他干预的完整结果请在回放大脑中检查，或导出设计。':'These are submitted multipliers and neuron parameters. Inspect the replay brain or export the design for the combined effects of overlapping circuits, edge changes and other interventions.'}</p></details>
  <p className="training-hint">{zh?'这些是训练场景里的实际记录。吃到更多或短时不倒置，仍不能证明持续觅食或在新环境中同样有效。':'These are actual training-condition records. More food or a short upright interval does not establish sustained foraging or success in a new environment.'}</p>
 </section>
}
