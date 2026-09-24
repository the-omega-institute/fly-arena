import {useEffect,useRef,type ReactNode} from 'react'
import {X} from 'lucide-react'
import {useI18n} from '../../shared/i18n'
import './guide.css'

/** Keep the reference manual outside the workspace; native dialog provides focus containment. */
export function GuideHelpDialog({onClose,children}:{onClose:()=>void;children:ReactNode}){
 const ref=useRef<HTMLDialogElement>(null)
 const {locale}=useI18n(),zh=locale==='zh-CN'
 useEffect(()=>{
  const dialog=ref.current!,opener=document.activeElement as HTMLElement|null
  if(dialog.showModal)dialog.showModal()
  else dialog.setAttribute('open','')
  dialog.querySelector<HTMLButtonElement>('button')?.focus()
  return()=>{if(dialog.open)dialog.close?.();if(opener?.isConnected)opener.focus()}
 },[])
 return <dialog ref={ref} className="guide-help-dialog" aria-labelledby="guide-help-title" onCancel={event=>{event.preventDefault();onClose()}}>
  <header className="guide-help-header"><h2 id="guide-help-title">{zh?'玩法与科学说明':'How to play and the science behind it'}</h2><button className="icon-button" onClick={onClose} aria-label={zh?'关闭帮助':'Close help'}><X size={20}/></button></header>
  {children}
 </dialog>
}
