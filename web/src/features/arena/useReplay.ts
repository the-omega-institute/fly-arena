import {useEffect,useState} from 'react'
import {api} from '../../api'
import {emptyReplay,requestReplay,type ReplayState} from './replayRequest'

export function useReplay(matchId:string,status:string|undefined) {
  const [replay,setReplay] = useState<ReplayState>(()=>emptyReplay(matchId,'idle'))
  useEffect(()=>{
    if (status!=='verified') {setReplay(emptyReplay(matchId,'idle'));return}
    const request = requestReplay(matchId,api,setReplay)
    return request.cancel
  },[matchId,status])
  // Hide obsolete data during the render itself, before effect cleanup runs.
  if (status!=='verified') return emptyReplay(matchId,'idle')
  return replay.matchId===matchId ? replay : emptyReplay(matchId,'loading')
}
