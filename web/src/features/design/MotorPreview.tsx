import {useI18n} from '../../shared/i18n'

export type MotorSample={raw:number[];clipped:number[];drive:number[]}
export type MotorReadout={available:boolean;reason?:string;id?:string;calibration_model?:string;readout_sha256?:string}
type TimedMotor={time_ms:number;motor?:MotorSample|null;reference_motor?:MotorSample|null}
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)
const show=(v:unknown)=>finite(v)?v.toFixed(3):'—'

export function MotorPreview({samples,sample,readout,duration,onset,offset,pulse}:{samples:TimedMotor[];sample:TimedMotor;readout?:MotorReadout;duration:number;onset:number;offset:number;pulse:boolean}){
 const {locale}=useI18n(),zh=locale==='zh-CN'
 if(!readout?.available)return <p className="stimulus-preview__motor-missing">{zh?'这份记录没有可用的运动读出；不从脑区平均活动估算动作。':'This record has no available motor readout; actions are not inferred from population averages.'}</p>
 const x=(ms:number)=>40+ms/Math.max(1,duration)*270,y=(value:number)=>116-value/1.5*90
 function line(channel:number,reference:boolean){let pen=false;return samples.map(s=>{const v=(reference?s.reference_motor:s.motor)?.drive?.[channel];if(!finite(v)){pen=false;return ''}const point=`${pen?'L':'M'}${x(s.time_ms)},${y(v)}`;pen=true;return point}).join(' ')}
 return <section className="stimulus-preview__motor" aria-label={zh?'设计与 WT 运动指令':'Design and WT motor commands'}>
  <h3>{zh?'大脑输出 → 左右运动指令':'Brain output → bilateral motor commands'}</h3>
  <p>{zh?'共享冻结解码器读取实际下行神经元活动，生成左右驱动。实线为设计，虚线为 WT，两侧纵轴都固定为 0–1.5。拖动上方时间轴可同时查看脑活动与指令。':'The shared frozen decoder reads actual descending-neuron activity. Solid lines show your design; dashed lines show WT. Both channels use a fixed 0–1.5 axis. Scrub the timeline above to inspect brain activity and commands together.'}</p>
  <div className="stimulus-preview__motor-grid">{[0,1].map(channel=><div key={channel}>
   <h4>{channel===0?(zh?'左侧驱动':'Left drive'):(zh?'右侧驱动':'Right drive')}</h4>
   <svg viewBox="0 0 330 147" role="img" aria-label={`${channel===0?'Left':'Right'} motor drive curves`}>
    {pulse&&<rect x={x(onset)} y="26" width={x(offset)-x(onset)} height="90" fill="var(--accent)" opacity=".09"/>}
    {[0,.75,1.5].map(v=><g key={v}><path d={`M40 ${y(v)}H310`} stroke="currentColor" opacity=".12"/><text x="34" y={y(v)+4} textAnchor="end">{v}</text></g>)}
    <path d={line(channel,true)} fill="none" stroke="#bd8252" strokeWidth="2" strokeDasharray="5 4"/>
    <path d={line(channel,false)} fill="none" stroke="#398572" strokeWidth="2.5"/>
    <path d={`M${x(sample.time_ms)} 26V116`} stroke="currentColor" strokeDasharray="2 4"/>
    {[0,duration].map(ms=><text key={ms} x={x(ms)} y="138" textAnchor="middle">{ms} ms</text>)}
   </svg>
   <table><caption>{sample.time_ms} ms · {zh?'无量纲指令':'dimensionless commands'}</caption><thead><tr><th>{zh?'阶段':'Stage'}</th><th>{zh?'设计':'Design'}</th><th>WT</th></tr></thead><tbody>{(['raw','clipped','drive'] as const).map((key,i)=><tr key={key} data-motor-stage={key}><th>{(zh?['解码原值','限幅后','滤波驱动']:['Raw readout','Clipped','Filtered drive'])[i]}</th><td>{show(sample.motor?.[key]?.[channel])}</td><td>{show(sample.reference_motor?.[key]?.[channel])}</td></tr>)}</tbody></table>
  </div>)}</div>
  <p>{zh?'这里只显示运动指令，没有运行身体物理；数值不代表速度或已发生的转向。解码器在 LIF 上校准，换用其他神经模型的效果尚未验证。':'These are motor commands without body physics; values are not speeds or observed turns. The decoder was calibrated on LIF; transfer to other neural models is unvalidated.'} <code>{readout.id}</code></p>
 </section>
}
