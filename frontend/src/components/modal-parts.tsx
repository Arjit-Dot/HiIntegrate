import { useState, type ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Copy, Info, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'

// Building blocks for the content of a window, so every window is laid out the same way.

/** A titled block of a window. */
export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="mdl-section">
      <h3 className="mdl-section-title">{title}</h3>
      {hint && <p className="mdl-section-hint">{hint}</p>}
      {children}
    </section>
  )
}

/** Label and value rows, in a grid. A row whose value is null or undefined is left out. */
export function KeyValue({ rows }: { rows: [label: string, value: ReactNode][] }) {
  const shown = rows.filter(([, v]) => v !== null && v !== undefined && v !== '')
  return (
    <dl className="kv">
      {shown.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl>
  )
}

const ICONS = { success: CheckCircle2, failed: XCircle, warning: AlertTriangle, info: Info }

/** The headline of a result: a status, what happened in plain words, and optionally what to do next. */
export function Banner({ tone, title, children, next }: { tone: keyof typeof ICONS; title: string; children?: ReactNode; next?: ReactNode }) {
  const Icon = ICONS[tone]
  return (
    <div className={`banner ${tone}`} role={tone === 'failed' ? 'alert' : 'status'}>
      <Icon size={22} aria-hidden="true" className="banner-icon" />
      <div>
        <div className="banner-title">{title}</div>
        {children && <div className="banner-text">{children}</div>}
        {next && <div className="banner-next"><b>What to do:</b> {next}</div>}
      </div>
    </div>
  )
}

/** Something is in progress: a spinner and what is happening, including how long it may take. */
export function Loading({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <div><div className="loading-title">{title}</div>{hint && <div className="muted small">{hint}</div>}</div>
    </div>
  )
}

/** Raw data for people who want it: collapsed, with a Copy button. Never the main content. */
export function TechDetails({ title = 'Technical details', data, text, open = false }: { title?: string; data?: unknown; text?: string; open?: boolean }) {
  const [copied, setCopied] = useState(false)
  const body = text ?? JSON.stringify(data, null, 2)
  async function copy() {
    try { await navigator.clipboard.writeText(body); setCopied(true); setTimeout(() => setCopied(false), 1800) } catch { /* clipboard blocked: the text is still selectable */ }
  }
  return (
    <details className="tech" open={open}>
      <summary>{title}</summary>
      <div className="tech-body">
        <div className="tech-bar"><Button type="button" variant="secondary" size="sm" onClick={copy}><Copy size={13} style={{ marginRight: 6 }} />{copied ? 'Copied' : 'Copy'}</Button></div>
        <pre>{body}</pre>
      </div>
    </details>
  )
}

const shown = (v: unknown): string => (v === null || v === undefined ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v))

/** A record as a small table of field and value, instead of a block of JSON. */
export function RecordTable({ record, caption }: { record: Record<string, unknown> | null | undefined; caption?: string }) {
  if (!record) return null
  const entries = Object.entries(record)
  return (
    <table className="rectable">
      {caption && <caption>{caption}</caption>}
      <tbody>
        {entries.map(([k, v]) => <tr key={k}><th scope="row">{k}</th><td className="mono">{v === null || v === undefined || v === '' ? <span className="muted">empty</span> : shown(v)}</td></tr>)}
      </tbody>
    </table>
  )
}
