import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { SCHEMAS, type SchemaName } from '../lib/config'
import { ErrorBox, Pill } from '../components/common'
import { PAGE_SIZE, Pager } from '../components/Pager'

const tone = (v: unknown) => (v === 'active' || v === 'low' ? 'success' : v === 'inactive' || v === 'medium' ? 'degraded' : 'failed')

export default function Results() {
  const [schema, setSchema] = useState<SchemaName>('user')
  const [source, setSource] = useState('')
  const [view, setView] = useState<'table' | 'json'>('table')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<{ items: Record<string, unknown>[]; total: number } | null>(null)
  const [sources, setSources] = useState<string[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    setData(null)
    api.listResults({ target: schema, source, limit: PAGE_SIZE, offset })
      .then(r => {
        setData(r); setError('')
        // The API has no "list sources" route, so learn them from what comes back (keep the chosen one).
        setSources(prev => [...new Set([...prev, ...r.items.map(i => String(i.source))])].sort())
      })
      .catch(e => setError(e.message))
  }, [schema, source, offset])

  const cols = ['source', ...SCHEMAS[schema].fields, 'fetched_at']
  const rows = data?.items ?? []

  return (
    <section>
      <div className="page-head">
        <div><h1>Results</h1><p>Normalized records, one table per schema.</p></div>
        <div className="toolbar">
          <select value={schema} onChange={e => { setSchema(e.target.value as SchemaName); setSource(''); setSources([]); setOffset(0) }}>
            {(Object.keys(SCHEMAS) as SchemaName[]).map(s => <option key={s}>{s}</option>)}
          </select>
          <select value={source} onChange={e => { setSource(e.target.value); setOffset(0) }}>
            <option value="">All sources</option>{sources.map(s => <option key={s}>{s}</option>)}
          </select>
          <div className="seg">
            <button className={view === 'table' ? 'active' : ''} onClick={() => setView('table')}>Table</button>
            <button className={view === 'json' ? 'active' : ''} onClick={() => setView('json')}>JSON</button>
          </div>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      {view === 'json'
        ? <pre>{data === null ? 'Loading…' : JSON.stringify(rows, null, 2)}</pre>
        : (
          <div className="card tablewrap">
            <table>
              <thead><tr>{cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>
                {data === null && !error && <tr><td colSpan={cols.length} className="muted">Loading…</td></tr>}
                {data !== null && rows.length === 0 && <tr><td colSpan={cols.length} className="muted">No {schema} records yet. Run an integration that fills this table.</td></tr>}
                {rows.map((r, i) => (
                  <tr key={`${r.source}:${r.id}:${i}`}>
                    {cols.map(c => {
                      const v = r[c]
                      const badge = c === 'status' || c === 'severity'
                      return <td key={c} className={badge ? '' : 'small'}>
                        {v === undefined || v === null || v === '' ? <span className="muted">empty</span> : badge ? <Pill kind={tone(v)}>{String(v)}</Pill> : String(v)}
                      </td>
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {data && <Pager offset={offset} total={data.total} onChange={setOffset} />}
      <p className="note">Every record carries <code>source</code> and <code>fetched_at</code>, added by the platform. A record is identified by <code>(source, id)</code>.</p>
    </section>
  )
}
