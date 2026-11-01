import { useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, type QuarantineRecord } from '../api/client'
import { ErrorBox, Pill, useToast } from '../components/common'
import { PAGE_SIZE, Pager } from '../components/Pager'
import { FixWithAi } from '../components/FixWithAi'

const REASONS = ['missing_required_field', 'transform_failed', 'invalid_value']
const SCHEMA_NAMES = ['user', 'device', 'alert']

export default function Quarantine() {
  const [reason, setReason] = useState('')
  const [schema, setSchema] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<{ items: QuarantineRecord[]; total: number } | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [fixing, setFixing] = useState<{ integration: string; action: string } | null>(null)
  const [reload, setReload] = useState(0)
  const toast = useToast()

  useEffect(() => {
    setData(null)
    api.listQuarantine({ reason, target_schema: schema, limit: PAGE_SIZE, offset })
      .then(r => { setData(r); setError('') })
      .catch(e => setError(e.message))
  }, [reason, schema, offset, reload])

  async function exportAll() {
    setBusy(true)
    try {
      const text = await api.exportQuarantine({ reason, target_schema: schema })
      const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }))
      const a = document.createElement('a')
      a.href = url; a.download = 'quarantine.json'; a.click()
      URL.revokeObjectURL(url)
      toast('Exported every quarantined record that matches the filters')
    } catch (e) { toast(e instanceof Error ? e.message : 'Export failed') }
    finally { setBusy(false) }
  }

  const rows = data?.items ?? []
  // One "Fix with AI" per integration and action seen on this page: the fix covers every quarantined record of that action.
  const fixable = [...new Map(rows.map(q => [`${q.source}.${q.action}`, { integration: q.source, action: q.action, n: rows.filter(r => r.source === q.source && r.action === q.action).length }])).values()]
  return (
    <section>
      <div className="page-head">
        <div><h1>Quarantine</h1><p>Records that failed the rules. The run carried on without them.</p></div>
        <div className="toolbar">
          <select value={reason} onChange={e => { setReason(e.target.value); setOffset(0) }}>
            <option value="">All reasons</option>{REASONS.map(r => <option key={r}>{r}</option>)}
          </select>
          <select value={schema} onChange={e => { setSchema(e.target.value); setOffset(0) }}>
            <option value="">All schemas</option>{SCHEMA_NAMES.map(s => <option key={s}>{s}</option>)}
          </select>
          <Button onClick={exportAll} disabled={busy}>{busy ? 'Exporting…' : 'Export all (JSON)'}</Button>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {fixable.length > 0 && (
        <div className="callout">
          <strong><Sparkles size={14} style={{ verticalAlign: -2 }} /> Fix with AI</strong>
          <div className="hint" style={{ margin: '2px 0 8px' }}>The AI reads the rejected originals and proposes a change to the config. You see the change and how many records it would rescue before anything is applied.</div>
          <div className="inline" style={{ flexWrap: 'wrap' }}>
            {fixable.map(f => (
              <Button key={`${f.integration}.${f.action}`} variant="secondary" size="sm" type="button" onClick={() => setFixing({ integration: f.integration, action: f.action })}>
                {f.integration}.{f.action} <span className="muted" style={{ marginLeft: 6 }}>({f.n} on this page)</span>
              </Button>
            ))}
          </div>
        </div>
      )}
      <div className="card tablewrap">
        <table className="dense">
          <thead><tr><th>Source</th><th>Action</th><th>Schema</th><th>Run</th><th>Reason</th><th>Field</th><th>Quarantined at</th><th>Original record</th></tr></thead>
          <tbody>
            {data === null && !error && <tr><td colSpan={8} className="muted">Loading…</td></tr>}
            {data !== null && rows.length === 0 && <tr><td colSpan={8} className="muted">Nothing quarantined.</td></tr>}
            {rows.map((q, i) => (
              <tr key={`${q.run_id}:${i}`}>
                <td>{q.source}</td>
                <td className="mono small">{q.action}</td>
                <td><Pill kind="schema">{q.target_schema}</Pill></td>
                <td className="mono small nowrap">{q.run_id}</td>
                <td><Pill kind="failed">{q.reason}</Pill></td>
                <td className="mono small">{q.field ?? ''}</td>
                <td className="small">{new Date(q.created_at).toLocaleString()}</td>
                <td className="mono small"><div className="cell-wrap" title={JSON.stringify(q.raw)}>{JSON.stringify(q.raw)}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data && <Pager offset={offset} total={data.total} onChange={setOffset} />}
      {fixing && <FixWithAi {...fixing} onClose={() => setFixing(null)} onApplied={() => setReload(n => n + 1)} />}
      <p className="note">Export returns every quarantined record that matches the filters, in one file, not one page at a time.</p>
    </section>
  )
}
