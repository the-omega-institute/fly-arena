import {useState} from 'react'
import {useI18n} from '../../shared/i18n'
import {api} from '../../api'
type Sample={time:number;input_on:boolean;population:{mean_hz:number;active_count:number;above_400hz_count:number};circuits:Record<string,number>}
type Controls={neuron_count:number;recorded_count:number;conditions:{id:string;samples:Sample[]}[]}
export function WTControls(){
 const {locale}=useI18n(),zh=locale==='zh-CN';const [data,setData]=useState<Controls|null>(null),[error,setError]=useState(false),[loading,setLoading]=useState(false),[selected,setSelected]=useState('taste')
 async function load(){if(data||loading)return;setLoading(true);setError(false);try{setData(await api<Controls>('/observations/wt-controls'))}catch{setError(true)}finally{setLoading(false)}}
 const names:Record<string,string>=zh?{blank:'无刺激', 'odor-left':'左侧气味',taste:'味觉输入','touch-left':'左侧触觉','visual-left':'左侧视觉'}:{blank:'No stimulus','odor-left':'Left odor',taste:'Taste input','touch-left':'Left touch','visual-left':'Left vision'}
 const condition=data?.conditions.find(c=>c.id===selected),baseline=data?.conditions.find(c=>c.id==='blank')
 const max=Math.max(1,...(condition?.samples.map(s=>s.population.mean_hz)||[]),...(baseline?.samples.map(s=>s.population.mean_hz)||[]))
 const path=(samples:Sample[])=>samples.map((s,i)=>`${i?'L':'M'}${s.time/2*600},${110-s.population.mean_hz/max*95}`).join(' ')
 return <details className="wt-controls panel" onToggle={e=>{if(e.currentTarget.open)void load()}}><summary>{zh?'先看 WT 对照：刺激如何改变网络？':'WT controls: how does an input change the network?'}</summary>
 <p>{zh?'同一 WT 权重，每个条件独立重置；0.5–1.5 秒施加输入，其余时间关闭。这里是无身体的神经刺激实验，不是比赛，也不证明真实果蝇行为。':'Identical WT weights, independently reset for each condition. Input is on from 0.5–1.5 s. These are neural stimulus controls without a body, not matches or biological behavior validation.'}</p>
 {loading&&<p>{zh?'载入真实实验记录…':'Loading recorded controls…'}</p>}{error&&<p>{zh?'本部署尚未安装对照样本。':'Control samples are not installed on this deployment.'}<button onClick={()=>void load()}>{zh?'重试':'Retry'}</button></p>}
 {data&&<><div className="brain-event-jumps">{data.conditions.map(c=><button key={c.id} aria-pressed={selected===c.id} onClick={()=>setSelected(c.id)}>{names[c.id]||c.id}</button>)}</div><p>{data.neuron_count.toLocaleString()} {zh?'个神经元参与计算；记录':'neurons simulated; recorded'} {data.recorded_count} {zh?'个形态神经元。曲线为全网络平均活动。':'morphology neurons. Curves show the full-network mean activity.'}</p>
 <svg viewBox="0 0 600 130" role="img" aria-label={zh?'WT 刺激与无刺激活动对照':'WT stimulus versus no-input activity'}><rect x="150" y="0" width="300" height="115" fill="#85bc9a" opacity=".15"/><path d={path(baseline?.samples||[])} fill="none" stroke="#9aabb0" strokeWidth="2"/><path d={path(condition?.samples||[])} fill="none" stroke="#cf9f43" strokeWidth="2"/><text x="4" y="12" fill="currentColor" fontSize="10">{max.toFixed(2)} Hz</text><text x="150" y="127" fill="currentColor" fontSize="10">0.5 s · ON</text><text x="450" y="127" fill="currentColor" fontSize="10">1.5 s · OFF</text></svg>
 <p>{zh?'金色：所选条件；灰色：无刺激对照。着色区是输入开启时段。':'Gold: selected condition; gray: no-input control. Shading marks the input interval.'}</p>
 <table><thead><tr><th>{zh?'采样时刻':'Sample'}</th><th>{zh?'平均活动':'Mean activity'}</th><th>&gt; 1 Hz</th><th>&gt; 400 Hz</th></tr></thead><tbody>{[.5,1.5,2].map(t=>{const s=condition?.samples.find(s=>s.time===t);return s&&<tr key={t}><td>{t.toFixed(2)} s</td><td>{s.population.mean_hz.toFixed(3)} Hz</td><td>{s.population.active_count.toLocaleString()}</td><td>{s.population.above_400hz_count.toLocaleString()}</td></tr>})}</tbody></table></>}
 </details>
}
