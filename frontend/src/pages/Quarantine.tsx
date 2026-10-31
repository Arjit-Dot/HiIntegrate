import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { api, type QuarantineRecord } from '../api/client'
import { ErrorBox, Pill, useToast } from '../components/common'
import { PAGE_SIZE, Pager } from '../components/Pager'

const REASONS = ['missing_required_field', 'transform_failed', 'invalid_value']
const SCHEMA_NAMES = ['user', 'device', 'alert']

export default function Quarantine() {
  const [reason, setReason] = useState('')
  const [schema, setSchema] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<{ items: QuarantineRecord[]; total: number } | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  useEffect(() => {
    setData(null)
    api.listQuarantine({ reason, target_schema: schema, limit: PAGE_SIZE, offset })
      .then(r => { setData(r); setError('') })
      .catch(e => setError(e.message))
  }, [reason, schema, offset])

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
      <div className="card tablewrap">
        <table>
          <thead><tr><th>Source</th><th>Action</th><th>Schema</th><th>Run</th><th>Reason</th><th>Field</th><th>Quarantined at</th><th>Original record</th></tr></thead>
          <tbody>
            {data === null && !error && <tr><td colSpan={8} className="muted">Loading…</td></tr>}
            {data !== null && rows.length === 0 && <tr><td colSpan={8} className="muted">Nothing quarantined.</td></tr>}
            {rows.map((q, i) => (
              <tr key={`${q.run_id}:${i}`}>
                <td>{q.source}</td>
                <td className="mono small">{q.action}</td>
                <td><Pill kind="schema">{q.target_schema}</Pill></td>
                <td className="mono small">{q.run_id}</td>
                <td><Pill kind="failed">{q.reason}</Pill></td>
                <td className="mono small">{q.field ?? ''}</td>
                <td className="small">{new Date(q.created_at).toLocaleString()}</td>
                <td className="mono small">{JSON.stringify(q.raw)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data && <Pager offset={offset} total={data.total} onChange={setOffset} />}
      <p className="note">Export returns every quarantined record that matches the filters, in one file, not one page at a time.</p>
    </section>
  )
}
