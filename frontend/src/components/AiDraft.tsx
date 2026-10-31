import { useRef, useState } from 'react'
import { Paperclip, Sparkles, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, ApiError, type GenerateConfigResponse } from '../api/client'

// AI mode (D-14): a service name goes in, the AI finds the documentation, tries pages until one works, and drafts a config.
// A link or a file from this computer works too, for when the search cannot find the right page.
// Nothing is saved here. The draft opens in the normal form and editor, where a person reviews, tests and saves it.

const MAX_FILE = 1_500_000
const MAX_CHARS = 50_000
const TEXT_FILE = /\.(txt|md|markdown|json|ya?ml|html?|xml|curl|sh|log|csv)$/i
const BINARY_FILE = /\.(pdf|docx?|pptx?|xlsx?|png|jpe?g|gif|zip|gz)$/i

type Attached = { name: string; text: string; long: boolean }

// The last good draft per service is kept in this browser, so a demo can go on if the AI is busy or the network is down.
type SavedDraft = { response: GenerateConfigResponse; at: string }
const draftKey = (what: string, file: Attached | null) => `hiintegrate.draft.${(file ? `file:${file.name}` : what.trim().toLowerCase()) || 'none'}`
function loadDraft(key: string): SavedDraft | null {
  try { return JSON.parse(localStorage.getItem(key) ?? 'null') } catch { return null }
}
type Tried = NonNullable<GenerateConfigResponse['tried']>

export function AiDraft({ onDraft, initial = '' }: { onDraft: (r: GenerateConfigResponse) => void; initial?: string }) {
  const [what, setWhat] = useState(initial)   // a service name, or a link to documentation
  const [file, setFile] = useState<Attached | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [tried, setTried] = useState<Tried>([])
  const [off, setOff] = useState(false)
  const [savedDraft, setSavedDraft] = useState<SavedDraft | null>(null)
  const input = useRef<HTMLInputElement>(null)

  async function pick(f: File | undefined) {
    setError('')
    if (!f) return
    if (BINARY_FILE.test(f.name) || (!TEXT_FILE.test(f.name) && f.type && !f.type.startsWith('text/') && !f.type.includes('json') && !f.type.includes('yaml') && !f.type.includes('xml'))) {
      setError(`${f.name} is not a text file. PDF and Word files are not supported: save the page as HTML or text, or paste the part you need.`)
      return
    }
    if (f.size > MAX_FILE) { setError(`${f.name} is larger than 1.5 MB. Attach a smaller file, or just the part about the endpoints you need.`); return }
    const text = await f.text()
    if (!text.trim()) { setError(`${f.name} is empty.`); return }
    setFile({ name: f.name, text, long: text.length > MAX_CHARS })
  }

  async function generate() {
    setBusy(true); setError(''); setTried([]); setSavedDraft(null)
    try {
      const value = what.trim()
      const isLink = /^https?:\/\//i.test(value)
      const r = await api.generateConfig({
        ...(value ? (isLink ? { url: value } : { service: value }) : {}),
        ...(file ? { text: `Attached document (${file.name}):\n${file.text}` } : {}),
      })
      setTried(r.tried ?? [])
      try { localStorage.setItem(draftKey(what, file), JSON.stringify({ response: r, at: new Date().toISOString() })) } catch { /* private mode */ }
      onDraft(r)
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setOff(true)
      else {
        setSavedDraft(loadDraft(draftKey(what, file)))
        setError((e as Error).message)
        const t = (e instanceof ApiError ? (e.details as { tried?: Tried } | undefined)?.tried : undefined) ?? []
        setTried(t)
      }
    } finally { setBusy(false) }
  }

  if (off) {
    return <div className="callout"><strong>AI is switched off.</strong> The server has no <code>LLM_API_KEY</code>. Everything else works: use Manual mode.</div>
  }

  const ready = (what.trim() || file) && !busy
  return (
    <div className="card" style={{ padding: 18, marginBottom: 16 }}>
      <h2 style={{ marginTop: 0 }}><Sparkles size={16} style={{ verticalAlign: -2 }} /> Draft a config with AI</h2>
      <div className="hint" style={{ margin: '-4px 0 12px' }}>
        Type the name of the service. The AI finds its API documentation (trying several pages if it has to) and writes a draft, which fills in the form for you to check, test and save.
        If it cannot find the right page, paste a documentation link or attach a document from your computer. Nothing is saved until you press Save.
      </div>

      <label>Service name <span className="muted">(or a link to its API documentation)</span></label>
      <div className="inline">
        <input type="text" placeholder="Jira, Okta, GitHub, CrowdStrike…" value={what} onChange={e => setWhat(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && ready) generate() }} aria-label="Service name or documentation link" />
        <input ref={input} type="file" hidden accept=".txt,.md,.markdown,.json,.yaml,.yml,.html,.htm,.xml,.curl,.sh,text/*,application/json" aria-label="Attach a document"
          onChange={e => { pick(e.target.files?.[0]); e.target.value = '' }} />
        <Button variant="secondary" size="sm" type="button" title="Attach a document from this computer" aria-label="Attach a document from this computer" onClick={() => input.current?.click()}>
          <Paperclip size={16} />
        </Button>
      </div>
      {file && (
        <div className="inline" style={{ marginTop: 8 }}>
          <span className="pill" style={{ display: 'inline-flex', gap: 6, alignItems: 'center', background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}>
            <Paperclip size={12} /> {file.name} <span className="muted">({Math.round(file.text.length / 1000)}k characters)</span>
            <button type="button" title="Remove" aria-label="Remove the attached document" onClick={() => setFile(null)} style={{ all: 'unset', cursor: 'pointer', display: 'inline-flex' }}><X size={12} /></button>
          </span>
        </div>
      )}
      {file?.long && <div className="hint">Long file: only the first {MAX_CHARS.toLocaleString()} characters are used. Attach just the part about the endpoints you need if the rest is not relevant.</div>}
      {file && <div className="hint">With an attached document the AI reads it instead of searching the web.</div>}

      {error && <div className="hint err" role="alert" style={{ marginTop: 10 }}>{error}</div>}
      {error && savedDraft && (
        <div className="hint" style={{ marginTop: 6 }}>
          A draft for this was saved on {new Date(savedDraft.at).toLocaleString()}.{' '}
          <Button variant="secondary" size="sm" type="button" onClick={() => onDraft(savedDraft.response)}>Use the saved draft</Button>
        </div>
      )}
      {error && tried.length > 0 && (
        <div className="hint" style={{ marginTop: 6 }}>
          Pages the AI tried:
          <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
            {tried.map((t, i) => <li key={i}><code>{t.url}</code> <span className="muted">{t.ok ? 'used' : t.reason}</span></li>)}
          </ul>
        </div>
      )}
      <div className="inline" style={{ marginTop: 12 }}>
        <Button type="button" disabled={!ready} onClick={generate}>{busy ? 'Finding the documentation and drafting…' : 'Generate draft'}</Button>
        {busy && <span className="muted">This can take up to a minute.</span>}
      </div>
    </div>
  )
}
