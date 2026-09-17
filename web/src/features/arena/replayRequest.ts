import type {Frame,Scene} from '../../types'

export type ReplayState =
  | {matchId:string;status:'idle'|'loading';scene:null;frames:Frame[];error:''}
  | {matchId:string;status:'ready';scene:Scene;frames:Frame[];error:''}
  | {matchId:string;status:'error';scene:null;frames:Frame[];error:string}

export function emptyReplay(matchId:string,status:'idle'|'loading'):ReplayState {
  return {matchId,status,scene:null,frames:[],error:''}
}

type FetchReplay = <T>(path:string,options:RequestInit)=>Promise<T>
// Commit scene and frames together. The guard also handles transports that finish
// after abort, including a late failure from an obsolete request.
export function requestReplay(matchId:string,fetchReplay:FetchReplay,commit:(state:ReplayState)=>void) {
  const controller = new AbortController()
  let active = true
  commit(emptyReplay(matchId,'loading'))
  const path = '/matches/'+encodeURIComponent(matchId)
  const done = Promise.all([
    fetchReplay<Scene>(path+'/scene',{signal:controller.signal}),
    fetchReplay<Frame[]>(path+'/frames',{signal:controller.signal}),
  ]).then(([scene,frames])=>{
    if (!active) return
    if (!scene || !frames.length) throw new Error('Replay data is empty.')
    commit({matchId,status:'ready',scene,frames,error:''})
  }).catch(error=>{
    if (!active) return
    commit({matchId,status:'error',scene:null,frames:[],error:error instanceof Error?error.message:String(error)})
    controller.abort()
  })
  return {done,cancel:()=>{active=false;controller.abort()}}
}
