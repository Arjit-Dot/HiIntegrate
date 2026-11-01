import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { describe } from '../lib/errors'
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'

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

type ModalProps = {
  title: string
  subtitle?: string
  onClose: () => void
  children: ReactNode
  /** Buttons for the sticky footer: the primary action first on the right, then the secondary, then Close. */
  footer?: ReactNode
  size?: 'md' | 'lg' | 'xl'
  /** True when closing would lose something the person typed: asks first instead of closing. */
  dirty?: boolean
}
// Literal class names, so Tailwind sees them.
const SIZES = { md: 'sm:max-w-[640px]', lg: 'sm:max-w-[820px]', xl: 'sm:max-w-[1040px]' }

/** The one window every dialog in the app uses: title, one line saying what it is for, a scrolling body and a sticky footer.
 *  Esc, the X and a click outside all close it (after asking, if `dirty`). Focus stays inside it and returns to the button that opened it. */
export function Modal({ title, subtitle, onClose, children, footer, size = 'lg', dirty = false }: ModalProps) {
  const [asking, setAsking] = useState(false)
  // The button that opened this window, read before the window takes focus, so focus can go back to it when the window closes.
  const opener = useRef<HTMLElement | null>(document.activeElement instanceof HTMLElement ? document.activeElement : null)
  useEffect(() => () => {
    const el = opener.current
    if (el && el.isConnected && el !== document.body) setTimeout(() => el.focus(), 0)
  }, [])
  const tryClose = () => { if (dirty) setAsking(true); else onClose() }
  return (
    <Dialog open onOpenChange={o => !o && tryClose()}>
      <DialogContent className={`mdl flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 ${SIZES[size]}`}>
        <div className="mdl-head">
          <DialogTitle className="mdl-title">{title}</DialogTitle>
          {subtitle ? <DialogDescription className="mdl-sub">{subtitle}</DialogDescription> : <DialogDescription className="sr-only">{title}</DialogDescription>}
        </div>
        <div className="mdl-body">{children}</div>
        {(footer || asking) && (
          <div className="mdl-foot">
            {asking
              ? <>
                  <span className="mdl-foot-note">Close without saving? What you changed here will be lost.</span>
                  <Button variant="secondary" type="button" onClick={() => setAsking(false)}>Keep editing</Button>
                  <Button variant="destructive" type="button" onClick={onClose}>Discard and close</Button>
                </>
              : footer}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Confirm something with side effects, saying exactly what happens. Used instead of the browser's confirm(). */
export function ConfirmDialog({ title, subtitle, confirmLabel, cancelLabel = 'Cancel', danger = false, busy = false, onConfirm, onCancel, children }: {
  title: string; subtitle?: string; confirmLabel: string; cancelLabel?: string; danger?: boolean; busy?: boolean
  onConfirm: () => void; onCancel: () => void; children: ReactNode
}) {
  return (
    <Modal title={title} subtitle={subtitle} size="md" onClose={onCancel}
      footer={<>
        <Button variant="secondary" type="button" onClick={onCancel} disabled={busy}>{cancelLabel}</Button>
        <Button variant={danger ? 'destructive' : 'default'} type="button" onClick={onConfirm} disabled={busy}>{busy ? 'Working…' : confirmLabel}</Button>
      </>}>
      {children}
    </Modal>
  )
}

export const ErrorBox = ({ message, code }: { message: string; code?: string | null }) => {
  const info = describe(code, message)
  return (
    <div className="issue" role="alert"><div>
      <div className="p">{code ? info.title : 'Request failed'}</div>
      {code && <div style={{ marginBottom: 4 }}>{info.explain}</div>}
      <div className={code ? 'small' : undefined}>{message}</div>
      {code && <div className="small" style={{ marginTop: 4 }}><b>Next:</b> {info.next}</div>}
    </div></div>
  )
}
