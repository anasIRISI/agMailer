import * as DialogPrimitive from '@radix-ui/react-dialog'
import {X} from 'lucide-react'
import type {ReactNode} from 'react'
export function Dialog({open,onOpenChange,title,children}:{open:boolean;onOpenChange:(v:boolean)=>void;title:string;children:ReactNode}){return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}><DialogPrimitive.Portal><DialogPrimitive.Overlay className="modal-overlay"/><DialogPrimitive.Content className="modal-content" aria-describedby={undefined}><DialogPrimitive.Title className="modal-title">{title}</DialogPrimitive.Title><DialogPrimitive.Close className="modal-close" aria-label="Fermer"><X size={19}/></DialogPrimitive.Close>{children}</DialogPrimitive.Content></DialogPrimitive.Portal></DialogPrimitive.Root>}
