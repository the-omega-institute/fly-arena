import type {Identity} from './types'
let csrfToken:string|null=null
export function setCsrfToken(value:string|null){csrfToken=value}
export async function api<T>(path:string, options:RequestInit={}, identity?:Identity|null):Promise<T> {
  const response = await fetch('/api/v1'+path, {...options,credentials:'same-origin',headers:{'Content-Type':'application/json',...(identity?.token?{Authorization:`Bearer ${identity.token}`} :csrfToken?{'X-Arena-CSRF':csrfToken}:{}),...options.headers}})
  if(!response.ok){
    if(response.status===401)window.dispatchEvent(new Event('arena:session-expired'))
    const body=await response.json().catch(()=>({detail:`服务暂时不可用 (${response.status})`}))
    throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail))
  }
  return response.json()
}
