import type {ReactNode} from 'react'
import {Inbox,Loader2,AlertCircle} from 'lucide-react'
import {toast} from 'sonner'
export const statusLabels:Record<string,string>={draft:'Brouillon',pending:'En attente',running:'En cours',in_progress:'En cours',sent:'Accepté par Gmail',failed:'Échec',check:'À vérifier',cancelled:'Annulé',paused:'En pause',completed:'Terminée',simulated:'Simulé'}
export function Badge({status,children}:{status:string;children?:ReactNode}){return <span className={'badge badge-'+status}><span className="badge-dot"/>{children||statusLabels[status]||status}</span>}
export function Empty({title='Aucun élément pour le moment',text,action}:{title?:string;text:string;action?:ReactNode}){return <div className="empty"><div className="empty-icon"><Inbox size={25}/></div><h3>{title}</h3><p>{text}</p>{action}</div>}
export function Loading(){return <div className="empty"><Loader2 className="animate-spin"/><p>Chargement des données locales…</p></div>}
export function ErrorBox({error}:{error?:string}){return error?<div role="alert" className="error-box"><AlertCircle size={18}/>{error}</div>:null}
export async function run(action:()=>Promise<unknown>,success?:string){try{await action();if(success)toast.success(success);return true}catch(e){toast.error((e as Error).message);return false}}
export function PageTitle({eyebrow,title,description,action}:{eyebrow?:string;title:string;description:string;action?:ReactNode}){return <div className="page-title"><div><p className="eyebrow">{eyebrow||'VOTRE ESPACE CANDIDATURES'}</p><h1>{title}</h1><p className="muted">{description}</p></div>{action}</div>}
export function Progress({value}:{value:number}){return <div className="progress"><div style={{width:Math.min(100,value)+'%'}}/></div>}
