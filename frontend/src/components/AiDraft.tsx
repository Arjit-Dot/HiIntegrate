import { useRef, useState } from 'react'
import { Paperclip, Sparkles, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, ApiError, type GenerateConfigResponse } from '../api/client'

// AI mode (D-14): a documentation link, or a file from this computer, goes to the model, which drafts a config.
// Nothing is saved here. The draft opens in the normal form and editor, where a person reviews, tests and saves it.

const MAX_FILE = 1_500_000
const MAX_CHARS = 50_000
const TEXT_FILE = /\.(txt|md|markdown|json|ya?ml|html?|xml|curl|sh|log|csv)$/i
const BINARY_FILE = /\.(pdf|docx?|pptx?|xlsx?|png|jpe?g|gif|zip|gz)$/i

type Attached = { name: string; text: string; long: boolean }

export function AiDraft({ onDraft }: { onDraft: (r: GenerateConfigResponse) => void }) {
  const [url, setUrl] = useState('')
  const [extra, setExtra] = useState('')
  const [file, setFile] = useState<Attached | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [off, setOff] = useState(false)
  const [steps, setSteps] = useState<string[]>([])
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
    setBusy(true); setError(''); setSteps([])
    try {
      const attached = file ? `Attached document (${file.name}):\n${file.text}` : ''
      const text = [attached, extra.trim() && (file || url.trim() ? `Extra instructions: ${extra.trim()}` : extra.trim())].filter(Boolean).join('\n\n')
      const r = await api.generateConfig({ ...(url.trim() ? { url: url.trim() } : {}), ...(text ? { text } : {}) })
      setSteps((r.attempts ?? []).map(a => `Attempt ${a.attempt}: ${a.valid ? 'valid' : `${a.error_count} problem${a.error_count === 1 ? '' : 's'}`}`))
      onDraft(r)
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setOff(true)
      else setError((e as Error).message)
    } finally { setBusy(false) }
  }

  if (off) {
    return <div className="callout"><strong>AI is switched off.</strong> The server has no <code>LLM_API_KEY</code>. Everything else works: use Manual mode.</div>
  }

  const ready = (url.trim() || file) && !busy
  return (
    <div className="card" style={{ padding: 18, marginBottom: 16 }}>
      <h2 style={{ marginTop: 0 }}><Sparkles size={16} style={{ verticalAlign: -2 }} /> Draft a config with AI</h2>
      <div className="hint" style={{ margin: '-4px 0 12px' }}>
        Paste a link to the service&apos;s API documentation (a web page or an OpenAPI file), or attach a document from your computer if the link does not work.
        The AI writes a draft, which opens in the form for you to review, test and save. Nothing is saved until you do.
      </div>

      <label>Documentation URL</label>
      <div className="inline">
        <input type="url" className="mono" placeholder="https://docs.example.com/api" value={url} onChange={e => setUrl(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && ready) generate() }} aria-label="Documentation URL" />
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

      <div style={{ marginTop: 12 }}>
        <label>Anything else the AI should know <span className="muted">(optional)</span></label>
        <textarea placeholder="For example: only the endpoint that lists users, and the API uses an X-Api-Key header." value={extra} onChange={e => setExtra(e.target.value)} />
      </div>

      {error && <div className="hint err" role="alert" style={{ marginTop: 10 }}>{error}</div>}
      <div className="inline" style={{ marginTop: 12 }}>
        <Button type="button" disabled={!ready} onClick={generate}>{busy ? 'Reading and drafting…' : 'Generate draft'}</Button>
        {busy && <span className="muted">This can take up to a minute.</span>}
        {!busy && steps.length > 0 && <span className="muted">{steps.join(' · ')}</span>}
      </div>
    </div>
  )
}
