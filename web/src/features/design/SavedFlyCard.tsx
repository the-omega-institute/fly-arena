import {Bug} from 'lucide-react'
import type {CSSProperties} from 'react'
import type {Fly} from '../../types'
import {colors} from '../../types'
import {useI18n} from '../../shared/i18n'
import {flyIdentity} from '../../shared/flyIdentity'

export function SavedFlyCard({fly,viewer,selected,onClone}:{fly:Fly;viewer?:string;selected:boolean;onClone:(fly:Fly)=>void}){
 const {t}=useI18n();
 return <button className={'fly-card '+(selected?'selected':'')} onClick={()=>onClone(fly)} title={`${fly.name} · ${fly.id}`}>
  <div className="fly-avatar" style={{'--fly-color':colors[fly.color]} as CSSProperties}><Bug size={27} strokeWidth={1.1}/></div>
  <div><strong>{fly.name}</strong><small>{flyIdentity(fly,viewer,t)}</small><small><code>{fly.id.slice(0,8)}</code></small></div>
  {selected&&<span className="selected-dot"/>}
 </button>;
}
