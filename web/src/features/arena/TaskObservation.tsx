import type {Frame,Match} from '../../types'
import {useI18n} from '../../shared/i18n'

export function TaskObservation({match,frames,onSeek}:{match:Match;frames:Frame[];onSeek:(seconds:number)=>void}) {
  const {locale}=useI18n(),zh=locale==='zh-CN',task=match.result?.task
  if(!task)return null
  const maze=task.id==='maze-arrival-v1',arrival=task.arrival_seconds
  return <section className="arena-task-report panel" aria-label={zh?'任务观测结果':'Task observations'}>
    <span className="tiny-label">{maze?(zh?'单蝇基准 · 走迷宫':'SOLO BENCHMARK · LABYRINTH'):(zh?'双蝇对抗 · 接触与领地':'TWO-FLY ARENA · CONTACT & TERRITORY')}</span>
    <h3>{maze?(arrival==null?(zh?'观察结束，尚未到达终点':'Goal not reached during observation'):(zh?`首次到达 ${arrival.toFixed(2)} 秒`:`First arrival at ${arrival.toFixed(2)} s`)):(zh?`实际身体接触 ${task.contact_seconds.toFixed(2)} 秒`:`Physical body contact: ${task.contact_seconds.toFixed(2)} s`)}</h3>
    <p>{zh?'完整观察':'Observed'} <strong>{task.observed_seconds.toFixed(0)} s</strong> · {zh?'记录路径长度':'Recorded path length'} {task.path_length_mm.map(p=>p.toFixed(1)+' mm').join(' / ')}{!maze&&` · ${task.contact_bouts} ${zh?'次接触起始':'contact onsets'}`}</p>
    {maze?<p>{zh?'首次到达以口部与终点食物实际接触为准；未到达不会记成 0 秒。到达后仍持续记录，当前并未赋予果蝇路径规划器。':'Arrival requires actual mouth contact with the goal food; failure is never recorded as zero seconds. Observation continues after arrival. The fly has no built-in path planner.'}</p>:<p>{zh?'得分 = 独占中央区域的秒数。双方同时在中央不计分；接触、推挤来自物理模拟，目前没有专门的扑击、抓抱或伤害动作。':'Score = seconds of exclusive center occupancy. Both flies inside earn no points. Contact and pushing come from physics; dedicated lunging, grappling and injury actions are not implemented.'}</p>}
    <div className="replay-camera-controls"><button onClick={()=>onSeek(0)}>{zh?'从头观察':'Watch from start'}</button>{arrival!=null&&<button onClick={()=>onSeek(Math.max(0,arrival-.5))}>{zh?'跳到首次到达前':'Before first arrival'}</button>}{[60,120,180].filter(t=>t<=frames[frames.length-1].time).map(t=><button key={t} onClick={()=>onSeek(t)}>{t/60}:00</button>)}</div>
    <small>{zh?'地面细线是实际记录位置的投影。长回放身体与脑活动每 50 ms 采样；这不是连续膜电位录像。两种任务关闭游戏能量耗尽停机，仍完整计算神经和物理状态。':'Ground trails project recorded positions. Long replays sample body and brain every 50 ms; this is not a continuous membrane-voltage recording. Both tasks disable the game energy cutoff while retaining full neural and physical integration.'}</small>
  </section>
}
