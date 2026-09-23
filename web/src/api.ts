import type {Identity} from './types'
/** Static hosts supply a public API origin in index.html; local deployments stay same-origin. */
export function apiOrigin(){return (typeof document==='undefined'?'':document.querySelector<HTMLMetaElement>('meta[name="arena-api-origin"]')?.content||'').replace(/\/$/,'')}
export function serviceUrl(path:string){return apiOrigin()+path}
let csrfToken:string|null=null
export function setCsrfToken(value:string|null){csrfToken=value}
export async function api<T>(path:string, options:RequestInit={}, identity?:Identity|null):Promise<T> {
  const response = await fetch(serviceUrl('/api/v1'+path), {...options,credentials:'same-origin',headers:{'Content-Type':'application/json',...(identity?.token?{Authorization:`Bearer ${identity.token}`} :csrfToken?{'X-Arena-CSRF':csrfToken}:{}),...options.headers}})
  if(!response.ok){
    if(response.status===401)window.dispatchEvent(new Event('arena:session-expired'))
    const body=await response.json().catch(()=>({detail:`HTTP ${response.status}`}))
    throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail))
  }
  return response.json()
}

/** getRandomValues also works on LAN HTTP origins where randomUUID is unavailable. */
export function newRequestKey(){
  const bytes=globalThis.crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('')
}
