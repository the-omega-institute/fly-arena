import './brain-model.css'
import {useI18n} from '../../shared/i18n'
export const LIF='malecns-lif-cpu-v1'
export const RATE='malecns-rate-cpu-v1'
export function BrainModelPicker({value,onChange}:{value:string;onChange:(id:string)=>void}){
 const {locale}=useI18n();const c=(en:string,zh:string)=>locale==='en'?en:zh
 return <fieldset className="brain-model-picker"><legend>{c('Brain dynamics','大脑运行模型')}</legend><label><input type="radio" name="brain-model" checked={value===LIF} onChange={()=>onChange(LIF)}/><span><strong>{c('LIF · discrete spikes','LIF · 离散脉冲')}</strong><small>{c('Membrane potential, refractory period and delayed synaptic events.','膜电位、不应期与延迟突触事件。')}</small></span></label><label><input type="radio" name="brain-model" checked={value===RATE} onChange={()=>onChange(RATE)}/><span><strong>{c('Continuous rate · experimental','连续发放率 · 实验模型')}</strong><small>{c('The same anatomical graph, continuous neural activity; supports response-gradient training.','沿用相同解剖连接图，以连续活动运行，支持响应梯度训练。')}</small></span></label><p>{value===RATE?c('Uses the frozen LIF motor decoder experimentally. No discrete spikes or within-match learning. Adam fits a teaching response; arena matches measure actual performance.','实验性复用固定的 LIF 运动读出器。不产生离散脉冲，比赛内不学习。Adam 拟合教学响应，竞技场再测实际表现。'):c('Choose the weight optimizer in Training after saving. Changing model preserves parameters and records the parent.','保存后在训练页选择权重优化算法。切换模型保留参数与父代记录。')}</p></fieldset>
}
