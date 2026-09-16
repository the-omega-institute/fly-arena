export type Tab='design'|'arena'|'lab'|'code'
export function readRoute(hash:string){const p=new URLSearchParams(hash.replace(/^#/,''));const experiment=p.get('experiment')||'';const match=p.get('match')||'';const value=p.get('tab');const tab:Tab=experiment?'lab':match?'arena':value==='arena'||value==='lab'||value==='code'?value:'design';return {tab,experiment,match}}
export function routeHash(tab:Tab,experiment='',match=''){const p=new URLSearchParams({tab});if(tab==='lab'&&experiment)p.set('experiment',experiment);if(tab==='arena'&&match)p.set('match',match);return '#'+p.toString()}
