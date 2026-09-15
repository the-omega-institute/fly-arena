import type {Identity} from './types'
export async function api<T>(path:string, options:RequestInit={}, identity?:Identity|null):Promise<T> {
  const response = await fetch('/api/v1'+path, {...options,headers:{'Content-Type':'application/json',...(identity?{Authorization:`Bearer ${identity.token}`} :{}),...options.headers}})
  if(!response.ok){
    const body=await response.json().catch(()=>({detail:`服务暂时不可用 (${response.status})`}))
    throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail))
  }
  return response.json()
}
