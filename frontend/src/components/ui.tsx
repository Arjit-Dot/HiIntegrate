import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

export const Pill = ({ kind, children }: { kind: string; children: ReactNode }) => <span className={`pill ${kind}`}>{children}</span>

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
    <div className="modal-bg open" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head"><h2>{title}</h2><button className="btn secondary small" onClick={onClose}>Close</button></div>
        {children}
      </div>
    </div>
  )
}

export const ErrorBox = ({ message }: { message: string }) => (
  <div className="issue"><div><div className="p">Error</div><div>{message}</div></div></div>
)
