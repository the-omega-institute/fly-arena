import {useMemo,useState} from 'react'
import type {ReplayParticipant,Spec} from '../../types'
import {useI18n} from '../../shared/i18n'
import {draftFromReplay,type ReplayDesignOrigin} from './replayDesign'

export function ReplayDesignActions({participant,matchId,onDesign}:{participant?:ReplayParticipant;matchId:string;onDesign?:(draft:Spec,origin:ReplayDesignOrigin)=>void}){
 const {locale}=useI18n(),zh=locale==='zh-CN'
 const [error,setError]=useState('')
 const draft=useMemo(()=>{try{return participant?draftFromReplay(participant):null}catch{return null}},[participant])
 if(!draft||!participant)return <p className="replay-design-missing">{zh?'这份回放没有可用的参赛设计快照，暂不能从它创建草稿。':'This replay has no usable participant design snapshot to start a draft.'}</p>
 function download(){
  try{
   setError('')
   const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}))
   const link=document.createElement('a');link.href=url;link.download=`fly-${participant!.id}-child.flyspec.json`;link.click()
   setTimeout(()=>URL.revokeObjectURL(url),1000)
  }catch{setError(zh?'下载未完成，请重试。':'Download failed. Please try again.')}
 }
 return <div className="replay-design-actions">
  <div><button className="secondary" aria-label={zh?'以这份大脑开始设计':'Design from this brain'} disabled={!onDesign} onClick={()=>onDesign?.(draft,{matchId,flyId:participant.id,name:participant.name})}>{zh?'以这份大脑开始设计':'Design from this brain'} →</button><button className="text-link" onClick={download}>{zh?'下载草稿给 AI':'Download draft for AI'}</button></div>
  <p>{zh?'将本场参赛的神经设计复制为草稿，保留它作为亲代。修改并保存后，再选择算法训练或参赛。感觉配置和动作读出属于实验条件，不随设计复制。':'Copy this participant’s recorded neural design into a draft with this fly as its parent. Edit and save, then choose training or competition. Sensory settings and motor readout are experiment conditions and are not copied with the design.'}</p>
  {error&&<p role="status">{error}</p>}
 </div>
}
