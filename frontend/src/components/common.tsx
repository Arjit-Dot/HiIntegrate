import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

export const Pill = ({ kind, children }: { kind: string; children: ReactNode }) => (
  <Badge variant={kind as never}>{children}</Badge>
)

const ToastCtx = createContext<(msg: string) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState('')
  const [show, setShow] = useState(false)
  const timer = useRef<number>(0)
  const toast = useCallback((m: string) => {
    setMsg(m); setShow(true)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setShow(false), 2600)
  }, [])
  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className={`toast${show ? ' show' : ''}`}>{msg}</div>
    </ToastCtx.Provider>
  )
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent className="max-h-[88vh] max-w-[720px] overflow-auto sm:max-w-[720px]" aria-describedby={undefined}>
        <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  )
}

export const ErrorBox = ({ message }: { message: string }) => (
  <div className="issue"><div><div className="p">Error</div><div>{message}</div></div></div>
)
