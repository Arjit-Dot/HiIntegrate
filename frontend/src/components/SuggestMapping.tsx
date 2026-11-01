import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, ApiError, type MappingSuggestion } from '../api/client'
import { TRANSFORMS, type MapRow, type SchemaName } from '../lib/config'
import { Modal, Pill } from './common'
import { Banner, Loading, RecordTable, Section } from './modal-parts'

// AI mapping suggestions (D-14). Paste a sample response: the AI suggests where each field of the schema comes from, and the
// platform checks every suggestion against the real records. The person accepts or edits each row, sees the record as it would
// be saved, and applies the rows to the form. Nothing is saved here.

type Row = MappingSuggestion['fields'][number] & { accept: boolean; valueMap: string }
const vmText = (m: Record<string, string> | null | undefined) => Object.entries(m ?? {}).map(([k, v]) => `${k}=${v}`).join(', ')
const parseVM = (t: string): Record<string, string> | null => {
  const out: Record<string, string> = {}
  t.split(',').map(x => x.trim()).filter(Boolean).forEach(p => { const i = p.indexOf('='); if (i > 0) out[p.slice(0, i).trim()] = p.slice(i + 1).trim() })
  return Object.keys(out).length ? out : null
}
const tone = (c: string) => (c === 'high' ? 'success' : c === 'medium' ? 'degraded' : 'failed')
const shown = (v: unknown) => (v === null || v === undefined ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v))

export function SuggestMapping({ schema, current, onApply, onClose }: {
  schema: SchemaName
  current: Record<string, MapRow>
  onApply: (rows: { field: string; path: string; transform: string; valueMap: string }[], recordsPath: string) => void
  onClose: () => void
}) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [off, setOff] = useState(false)
  const [result, setResult] = useState<MappingSuggestion | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [sample, setSample] = useState<unknown>(null)

  function parse(): unknown | undefined {
    try { return JSON.parse(text) } catch { setError('The sample must be JSON: paste a response from the service (a list of records, or an object that holds one).'); return undefined }
  }
  function show(r: MappingSuggestion, keep?: Row[]) {
    setResult(r)
    setRows(r.fields.map(f => ({ ...f, accept: keep?.find(k => k.field === f.field)?.accept ?? f.confidence !== 'low', valueMap: vmText(f.value_map) })))
  }

  async function suggest() {
    const s = parse(); if (s === undefined) return
    setBusy(true); setError(''); setResult(null)
    try { setSample(s); show(await api.suggestMapping({ target_schema: schema, sample: s })) }
    catch (e) { if (e instanceof ApiError && e.status === 501) setOff(true); else setError((e as Error).message) }
    finally { setBusy(false) }
  }

  // No model: check what is in the rows (or, before any suggestion, what the form already has) against the sample.
  async function check(fromForm = false) {
    const s = parse(); if (s === undefined) return
    setBusy(true); setError('')
    try {
      const mapping = fromForm
        ? Object.fromEntries(Object.entries(current).filter(([, m]) => m.path).map(([f, m]) => [f, { path: m.path, transform: m.transform || null, value_map: parseVM(m.valueMap) }]))
        : Object.fromEntries(rows.map(r => [r.field, { path: r.path, transform: r.transform || null, value_map: parseVM(r.valueMap) }]))
      setSample(s); show(await api.suggestMapping({ target_schema: schema, sample: s, mapping }), fromForm ? undefined : rows)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  const set = (field: string, patch: Partial<Row>) => setRows(prev => prev.map(r => (r.field === field ? { ...r, ...patch } : r)))
  const chosen = rows.filter(r => r.accept && r.path.trim())

  return (
    <Modal title="Suggest the field mapping with AI" subtitle={`Show the AI a sample reply and it suggests where each ${schema} field comes from. Nothing is saved from here.`}
      onClose={onClose} size="xl" dirty={chosen.length > 0 && !!result}
      footer={result
        ? <>
            <span className="mdl-foot-note">This only fills the form. Press <b>Test connection</b> or <b>Save</b> there when you are ready.</span>
            <Button type="button" variant="secondary" onClick={onClose}>Close without applying</Button>
            <Button type="button" disabled={chosen.length === 0}
              onClick={() => { onApply(chosen.map(r => ({ field: r.field, path: r.path.trim(), transform: r.transform ?? '', valueMap: r.valueMap })), result.records_path); onClose() }}>
              Apply {chosen.length} row{chosen.length === 1 ? '' : 's'} to the form
            </Button>
          </>
        : <Button type="button" variant="secondary" onClick={onClose}>Close</Button>}>
      <Section title="1. The sample reply" hint="Paste what the service returns, as JSON. Names and emails in it are hidden from the AI.">
        <textarea className="mono" rows={8} placeholder={'{ "data": [ { "accountId": "5b10a2", "displayName": "Ada", "emailAddress": "ada@example.com" } ] }'}
          value={text} onChange={e => { setText(e.target.value); setError('') }} aria-label="Sample response" aria-invalid={!!error || undefined} />
        <div className="inline" style={{ marginTop: 12, flexWrap: 'wrap' }}>
          <Button type="button" onClick={suggest} disabled={busy || !text.trim() || off}><Sparkles size={14} style={{ marginRight: 6 }} />{busy ? 'Working…' : 'Suggest with AI'}</Button>
          <Button type="button" variant="secondary" onClick={() => check(true)} disabled={busy || !text.trim()} title="No AI: check the paths already in the form against this sample">Check the form&apos;s current mapping</Button>
        </div>
      </Section>
      {off && <Banner tone="info" title="AI is switched off">The server has no <code>LLM_API_KEY</code>. You can still paste a sample and check the paths already in the form against it.</Banner>}
      {busy && <Loading title="Working on it…" hint="Asking the AI can take about 10 seconds. Checking paths only takes a moment." />}
      {error && <Banner tone="failed" title="That did not work" next="Fix the sample (it must be valid JSON with at least one record) and try again.">{error}</Banner>}

      {result && (
        <>
          <div className="hint">Records found in the sample: <b>{result.records_found}</b>{result.records_path !== '@' && <> (under <code>{result.records_path}</code>)</>}.</div>
          <div className="tablewrap" style={{ margin: '8px 0' }}>
            <table>
              <thead><tr><th></th><th>Field</th><th>Path in the record</th><th>Transform</th><th>Value map</th><th>Check</th></tr></thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.field}>
                    <td><input type="checkbox" checked={r.accept} onChange={e => set(r.field, { accept: e.target.checked })} aria-label={`Use the suggestion for ${r.field}`} /></td>
                    <td><b>{r.field}</b><div><Pill kind={tone(r.confidence)}>{r.confidence}</Pill></div></td>
                    <td><input type="text" className="mono" value={r.path} aria-invalid={!r.valid || undefined} onChange={e => set(r.field, { path: e.target.value })} />
                      {r.reason && <div className="hint">{r.reason}</div>}</td>
                    <td><select value={r.transform ?? ''} onChange={e => set(r.field, { transform: e.target.value || null })}>{TRANSFORMS.map(t => <option key={t} value={t}>{t || 'none'}</option>)}</select></td>
                    <td><input type="text" className="mono" placeholder="ACTIVE=active" value={r.valueMap} onChange={e => set(r.field, { valueMap: e.target.value })} /></td>
                    <td className="small">{!r.valid ? <span className="hint err">not a valid path</span> : <>{r.found} of {r.of}{r.example !== null && r.example !== undefined && <div className="muted mono">{shown(r.example).slice(0, 40)}</div>}</>}</td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={6} className="muted">Nothing could be mapped from this sample.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="inline" style={{ flexWrap: 'wrap' }}>
            <Button type="button" variant="secondary" size="sm" onClick={() => check(false)} disabled={busy || sample === null}>Re-check my edits</Button>
            <span className="hint">Edit a path or transform, then re-check to see the new example and the preview.</span>
          </div>

          {'record' in result.preview
            ? <Section title="2. The first record would be saved as"><RecordTable record={result.preview.record as Record<string, unknown>} /></Section>
            : <Banner tone="warning" title="The first record would be quarantined" next="Fix that row (or untick it), then press Re-check my edits.">
                Reason: <Pill kind="failed">{result.preview.quarantine.reason}</Pill> on <code>{result.preview.quarantine.field}</code>.
              </Banner>}
        </>
      )}
    </Modal>
  )
}
