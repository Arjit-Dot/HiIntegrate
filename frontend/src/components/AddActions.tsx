import { useEffect, useRef, useState } from 'react'
import * as yaml from 'js-yaml'
import { Button } from '@/components/ui/button'
import type { Config, GenerateConfigResponse } from '../api/client'
import { Pill } from './common'
import { AiDraft } from './AiDraft'

// Add several actions to an integration at once (D-15: the integration is changed in place, saved with PUT).
// Actions come from the AI (a service name, a link or a document) or from an uploaded YAML or JSON file. Each is shown with a tick box,
// and the ticked ones are merged into the config being edited. Only the actions are taken: this integration's base URL,
// login and secret stay as they are. Nothing is saved until Save is pressed.

/** A full config (its `actions`), or just a map of actions. Returns the actions, or an error to show. */
export function actionsFrom(value: unknown): { actions?: Record<string, Config>; error?: string } {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { error: 'The file must hold a YAML or JSON object: a whole config, or just the actions.' }
  const obj = value as Config
  const map = obj.actions && typeof obj.actions === 'object' ? obj.actions : obj
  const entries = Object.entries<any>(map)
  if (entries.length === 0 || entries.some(([, a]) => !a || typeof a !== 'object' || !a.mode || !a.request)) {
    return { error: 'No actions found. Each action needs at least a mode and a request (a method and a path).' }
  }
  return { actions: Object.fromEntries(entries) }
}

export function AddActions({ existing, service, incoming, onAdd, onClose }: {
  existing: string[]                      // action names the integration already has, to tell new from replacing
  service?: string                        // prefills the AI box
  incoming?: Record<string, Config>       // actions already in hand (an AI draft sent here from the Add page)
  onAdd: (actions: Record<string, Config>) => void
  onClose: () => void
}) {
  const [found, setFound] = useState<Record<string, Config> | null>(incoming ?? null)
  const [ticked, setTicked] = useState<Set<string>>(new Set())
  const [source, setSource] = useState<'ai' | 'file'>(incoming ? 'file' : 'ai')
  const [fileName, setFileName] = useState('')
  const picker = useRef<HTMLInputElement>(null)
  const [error, setError] = useState('')

  // New actions start ticked. One with the name of an existing action would replace it, so it starts unticked.
  const existingKey = existing.join('\n')   // a stable value: `existing` is a new array on every render
  useEffect(() => { setTicked(new Set(Object.keys(found ?? {}).filter(n => !existingKey.split('\n').includes(n)))) }, [found, existingKey])

  async function readFile(f: File | undefined) {
    setError('')
    if (!f) return
    if (f.size > 1_000_000) { setError(`${f.name} is larger than 1 MB. Upload a file with just the actions.`); return }
    try {
      const text = await f.text()
      if (!text.trim()) { setError(`${f.name} is empty.`); return }
      const r = actionsFrom(yaml.load(text))
      if (r.error) setError(`${f.name}: ${r.error}`); else { setFileName(f.name); setFound(r.actions!) }
    } catch (e) { setError(`Could not read ${f.name}: ${(e as Error).message}`) }
  }
  function fromAi(r: GenerateConfigResponse) {
    const a = actionsFrom((r.config as Config | undefined)?.actions ? { actions: (r.config as Config).actions } : undefined)
    if (a.error) { setError('The AI draft has no actions. Try again, or upload a file.'); return }
    setError(''); setFound(a.actions!)
  }
  const toggle = (n: string) => setTicked(p => { const q = new Set(p); q.has(n) ? q.delete(n) : q.add(n); return q })

  const names = Object.keys(found ?? {})
  const chosen = names.filter(n => ticked.has(n))
  const replacing = chosen.filter(n => existing.includes(n))
  return (
    <div className="card" style={{ padding: 18, marginBottom: 16 }}>
      <div className="modal-head" style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Add several actions{service ? <> to <code>{service}</code></> : null}</h2>
        <Button variant="secondary" size="sm" type="button" onClick={onClose}>Close</Button>
      </div>
      {!found && (
        <>
          <div className="seg" style={{ marginBottom: 12 }}>
            <button type="button" className={source === 'ai' ? 'active' : ''} onClick={() => setSource('ai')}>With AI</button>
            <button type="button" className={source === 'file' ? 'active' : ''} onClick={() => setSource('file')}>Upload file</button>
          </div>
          {source === 'ai'
            ? <AiDraft onDraft={fromAi} initial={service} />
            : (
              <>
                <label>Actions file <span className="muted">(a whole config, or just the <code>actions:</code> part, as .yaml, .yml or .json)</span></label>
                <input ref={picker} type="file" hidden accept=".yaml,.yml,.json,text/yaml,application/json,text/*" aria-label="Upload a YAML or JSON file"
                  onChange={e => { readFile(e.target.files?.[0]); e.target.value = '' }} />
                <div role="button" tabIndex={0} className="mono"
                  style={{ border: '2px dashed var(--border, #cbd5e1)', borderRadius: 10, padding: '28px 16px', textAlign: 'center', cursor: 'pointer' }}
                  onClick={() => picker.current?.click()}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); picker.current?.click() } }}
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => { e.preventDefault(); readFile(e.dataTransfer.files?.[0]) }}>
                  <strong>Upload file</strong>
                  <div className="small muted" style={{ marginTop: 4 }}>Click to choose a file, or drop it here</div>
                </div>
              </>
            )}
          {error && <div className="hint err" role="alert" style={{ marginTop: 10 }}>{error}</div>}
        </>
      )}
      {found && (
        <>
          <div className="hint" style={{ marginBottom: 10 }}>
            {fileName && <>From <code>{fileName}</code>. </>}Found {names.length} action{names.length === 1 ? '' : 's'}. Tick the ones to add. This integration&apos;s base URL, login and secret are <b>not</b> changed. If an action uses a variable
            you have not set, the form will say so.
          </div>
          {names.map(n => {
            const a = found[n], clash = existing.includes(n)
            return (
              <label key={n} className="inline" style={{ margin: '0 0 8px', fontWeight: 400, alignItems: 'flex-start' }}>
                <input type="checkbox" checked={ticked.has(n)} onChange={() => toggle(n)} style={{ marginTop: 4 }} />
                <span>
                  <span className="mono name">{n}</span>{' '}
                  <Pill kind={a.mode}>{a.mode}</Pill>{' '}<Pill kind="schema">{a.target_schema}</Pill>{' '}
                  {clash ? <Pill kind="degraded">replaces the existing {n}</Pill> : <Pill kind="healthy">new</Pill>}
                  <div className="mono small muted">{a.request?.method ?? 'GET'} {a.request?.path}</div>
                </span>
              </label>
            )
          })}
          {replacing.length > 0 && <div className="hint err">{replacing.join(', ')} will be overwritten by the version above.</div>}
          <div className="inline" style={{ marginTop: 12 }}>
            <Button type="button" disabled={chosen.length === 0} onClick={() => onAdd(Object.fromEntries(chosen.map(n => [n, found[n]])))}>
              Add {chosen.length} action{chosen.length === 1 ? '' : 's'} to the form
            </Button>
            {!incoming && <Button variant="secondary" type="button" onClick={() => { setFound(null); setError('') }}>Start over</Button>}
          </div>
        </>
      )}
    </div>
  )
}
