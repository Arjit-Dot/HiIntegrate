import { useEffect, useState } from 'react'
import { api, type UnifiedUser } from '../api/client'
import { SCHEMAS, type SchemaName } from '../lib/config'
import { ErrorBox, Pill } from '../components/common'
import { PAGE_SIZE, Pager } from '../components/Pager'
import { SummaryButton, SummaryCard, useSummary } from '../components/SummaryPanel'

const tone = (v: unknown) => (v === 'active' || v === 'low' ? 'success' : v === 'inactive' || v === 'medium' ? 'degraded' : 'failed')
const when = (v: string | null | undefined) => (v ? new Date(v).toLocaleString() : null)
const Empty = () => <span className="muted">empty</span>

type Rows = { items: Record<string, unknown>[] | UnifiedUser[]; total: number }

export default function Results() {
  const [schema, setSchema] = useState<SchemaName>('user')
  // Users can be shown one row per person (D-16, the default) or one row per stored record.
  const [people, setPeople] = useState(true)
  const [source, setSource] = useState('')
  const [view, setView] = useState<'table' | 'json'>('table')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<Rows | null>(null)
  const [sources, setSources] = useState<string[]>([])
  const [error, setError] = useState('')

  const unified = schema === 'user' && people
  const summary = useSummary(schema, source, unified ? undefined : data?.total)  // the People view counts people, not stored records

  useEffect(() => {
    setData(null)
    const learn = (names: string[]) => setSources(prev => [...new Set([...prev, ...names])].sort())
    const done = (r: Rows, names: string[]) => { setData(r); setError(''); learn(names) }
    // The API has no "list sources" route, so the source list is learned from what comes back (the chosen one is kept).
    const req = unified
      ? api.listUnifiedUsers({ source, limit: PAGE_SIZE, offset }).then(r => done(r, r.items.flatMap(u => u.sources.map(s => s.source))))
      : api.listResults({ target: schema, source, limit: PAGE_SIZE, offset }).then(r => done(r, r.items.map(i => String(i.source))))
    req.catch(e => setError(e.message))
  }, [schema, source, offset, unified])

  const cols = ['source', ...SCHEMAS[schema].fields, 'fetched_at']
  const rows = data?.items ?? []
  const width = unified ? 4 : cols.length

  return (
    <section>
      <div className="page-head">
        <div><h1>Results</h1><p>{unified ? 'One row per person, with every service they appear in.' : 'Normalized records, one table per schema.'}</p></div>
        <div className="toolbar">
          <select value={schema} onChange={e => { setSchema(e.target.value as SchemaName); setSource(''); setSources([]); setOffset(0) }}>
            {(Object.keys(SCHEMAS) as SchemaName[]).map(s => <option key={s}>{s}</option>)}
          </select>
          <select value={source} onChange={e => { setSource(e.target.value); setOffset(0) }}>
            <option value="">All sources</option>{sources.map(s => <option key={s}>{s}</option>)}
          </select>
          {schema === 'user' && (
            <div className="seg" title="People merges the same email across services. Records shows one row per service.">
              <button className={people ? 'active' : ''} onClick={() => { setPeople(true); setOffset(0) }}>People</button>
              <button className={!people ? 'active' : ''} onClick={() => { setPeople(false); setOffset(0) }}>Records</button>
            </div>
          )}
          <div className="seg">
            <button className={view === 'table' ? 'active' : ''} onClick={() => setView('table')}>Table</button>
            <button className={view === 'json' ? 'active' : ''} onClick={() => setView('json')}>JSON</button>
          </div>
          <SummaryButton s={summary} />
        </div>
      </div>
      <SummaryCard s={summary} />
      {error && <ErrorBox message={error} />}
      {view === 'json'
        ? <pre>{data === null ? 'Loading…' : JSON.stringify(rows, null, 2)}</pre>
        : (
          <div className="card tablewrap">
            <table>
              <thead><tr>{unified
                ? ['Person', 'Name', 'Services', 'Last login'].map(c => <th key={c}>{c}</th>)
                : cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>
                {data === null && !error && <tr><td colSpan={width} className="muted">Loading…</td></tr>}
                {data !== null && rows.length === 0 && <tr><td colSpan={width} className="muted">No {schema} records yet. Run an integration that fills this table.</td></tr>}
                {unified && (rows as UnifiedUser[]).map(u => (
                  <tr key={u.key}>
                    <td className="small">{u.email ?? <><span className="mono">{u.key}</span> <span className="muted">(no email)</span></>}</td>
                    <td>{u.name ?? <Empty />}</td>
                    <td>
                      {u.sources.map(s => (
                        <div key={`${s.source}:${s.id}`} className="small" style={{ marginBottom: 4 }}>
                          <Pill kind="schema">{s.source}</Pill> <code>{s.id}</code>{s.status && <> <Pill kind={tone(s.status)}>{s.status}</Pill></>}
                        </div>
                      ))}
                    </td>
                    <td className="small">{when(u.last_login) ?? <Empty />}</td>
                  </tr>
                ))}
                {!unified && (rows as Record<string, unknown>[]).map((r, i) => (
                  <tr key={`${r.source}:${r.id}:${i}`}>
                    {cols.map(c => {
                      const v = r[c]
                      const badge = c === 'status' || c === 'severity'
                      return <td key={c} className={badge ? '' : 'small'}>
                        {v === undefined || v === null || v === '' ? <Empty /> : badge ? <Pill kind={tone(v)}>{String(v)}</Pill> : String(v)}
                      </td>
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {data && <Pager offset={offset} total={data.total} onChange={setOffset} />}
      <p className="note">
        {unified
          ? <>People are matched by lowercased <code>email</code>. A user with no email stays on their own. Stored records are not changed: switch to <b>Records</b> to see one row per <code>(source, id)</code>.</>
          : <>Every record carries <code>source</code> and <code>fetched_at</code>, added by the platform. A record is identified by <code>(source, id)</code>.</>}
      </p>
    </section>
  )
}
