import { useEffect, useState } from 'react'
import { Sparkles, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, ApiError } from '../api/client'

// "Summarize" on the Results page (D-14). The server sends the model counts and a masked sample of the stored records
// and gets back a few plain sentences. Nothing is saved. The last good summary is kept in this browser, so the page can
// still show it (marked as saved) when the model is busy, and a demo does not depend on the model being up.

type Saved = { summary: string; at: string; total: number }
const key = (target: string, source: string) => `hiintegrate.summary.${target}.${source || 'all'}`

function load(target: string, source: string): Saved | null {
  try { return JSON.parse(localStorage.getItem(key(target, source)) ?? 'null') } catch { return null }
}

type Target = 'user' | 'device' | 'alert'

/** The state behind the button (in the page toolbar) and the card (under the page heading). */
export function useSummary(target: Target, source: string, total: number | undefined) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState<Saved | null>(null)
  const [fresh, setFresh] = useState(false)   // true when the text on screen was just written, false when it is the saved one
  const [error, setError] = useState('')
  const [off, setOff] = useState(false)

  // A different table or source: show what was saved for it (if anything), and nothing else until asked.
  useEffect(() => { setSaved(load(target, source)); setFresh(false); setError('') }, [target, source])

  async function run() {
    setOpen(true); setBusy(true); setError('')
    try {
      const { summary } = await api.summarize({ target, ...(source ? { source } : {}) })
      const next = { summary, at: new Date().toISOString(), total: total ?? 0 }
      try { localStorage.setItem(key(target, source), JSON.stringify(next)) } catch { /* private mode: still shown */ }
      setSaved(next); setFresh(true)
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setOff(true)
      else setError((e as Error).message)
      setFresh(false)
    } finally { setBusy(false) }
  }
  return { target, source, total, open, setOpen, busy, saved, fresh, error, off, run }
}
type Summary = ReturnType<typeof useSummary>

export function SummaryButton({ s }: { s: Summary }) {
  const empty = s.total === 0
  return (
    <Button variant="secondary" size="sm" type="button" onClick={() => (s.open && !s.busy ? s.setOpen(false) : s.run())}
      disabled={s.busy || empty} title={empty ? 'There are no records to summarize yet' : 'Ask the AI for a plain-language summary of these records'}>
      <Sparkles size={14} style={{ marginRight: 6 }} />{s.busy ? 'Summarizing…' : s.open ? 'Hide summary' : 'Summarize'}
    </Button>
  )
}

export function SummaryCard({ s }: { s: Summary }) {
  if (!s.open) return null
  const { saved, error, busy, off, fresh } = s
  return (
    <div className="callout" role="region" aria-label="AI summary">
      <div className="inline" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <strong><Sparkles size={14} style={{ verticalAlign: -2 }} /> Summary of {s.source ? <>{s.target} records from <code>{s.source}</code></> : <>all {s.target} records</>}</strong>
        <button type="button" title="Close" aria-label="Close the summary" onClick={() => s.setOpen(false)} style={{ all: 'unset', cursor: 'pointer', display: 'inline-flex' }}><X size={14} /></button>
      </div>
      {off && <p style={{ margin: '8px 0 0' }}><strong>AI is switched off.</strong> The server has no <code>LLM_API_KEY</code>. The records below are unaffected.</p>}
      {!off && busy && <p className="muted" style={{ margin: '8px 0 0' }}>Reading the records and writing the summary. This can take a few seconds.</p>}
      {!off && !busy && saved && <p style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }}>{saved.summary}</p>}
      {!off && !busy && error && (
        <div className="hint err" role="alert" style={{ marginTop: 8 }}>
          {error}{saved ? ' Showing the last saved summary above.' : ''}{' '}
          <Button variant="secondary" size="sm" type="button" onClick={s.run}>Try again</Button>
        </div>
      )}
      {!off && !busy && saved && !error && (
        <div className="hint" style={{ marginTop: 8 }}>
          {fresh ? 'Written just now' : `Saved summary from ${new Date(saved.at).toLocaleString()}`} {saved.total > 0 && <> from {saved.total.toLocaleString()} stored record{saved.total === 1 ? '' : 's'}</>}.
          {' '}It is a summary of the data, not a fact check: names and emails were hidden from the AI.{' '}
          {!fresh && <Button variant="secondary" size="sm" type="button" onClick={s.run}>Summarize again</Button>}
        </div>
      )}
    </div>
  )
}
