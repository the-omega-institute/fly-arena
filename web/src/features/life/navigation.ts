export const lifeHash=(id:string)=>'#tab=life&fly='+encodeURIComponent(id)
export const continueLifeHash=(id:string)=>'#tab=train&continue='+encodeURIComponent(id)
export function continuationFocus(hash:string){const id=new URLSearchParams(hash.replace(/^#/, '')).get('continue')||'';return /^[a-f0-9]{32}$/.test(id)?id:''}
