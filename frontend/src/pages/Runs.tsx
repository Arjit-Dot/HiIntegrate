import { useEffect, useState } from 'react'
import { api, type RunRecord } from '../api/client'
import { ErrorBox, Pill } from '../components/common'
import { PAGE_SIZE, Pager } from '../components/Pager'

const duration = (ms: number | null) => (ms === null ? '…' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`)

export default function Runs() {
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<{ items: RunRecord[]; total: number } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setData(null)
    api.listRuns({ status, limit: PAGE_SIZE, offset }).then(r => { setData(r); setError('') }).catch(e => setError(e.message))
  }, [status, offset])

  const rows = data?.items ?? []
  return (
    <section>
      <div className="page-head">
        <div><h1>Run history</h1><p>One row per run, newest first.</p></div>
        <div className="toolbar">
          <select value={status} onChange={e => { setStatus(e.target.value); setOffset(0) }}>
            <option value="">All statuses</option><option>running</option><option>success</option><option>failed</option>
          </select>
        </div>
      </div>
      {error && <ErrorBox message={error} />}
      <div className="card tablewrap">
        <table className="dense">
          <thead><tr><th>Run</th><th>Integration · action</th><th>Type</th><th>Status</th><th>Started</th><th>Pages</th><th>Pulled</th><th>Valid</th><th>Invalid</th><th>Retries</th><th>Error</th></tr></thead>
          <tbody>
            {data === null && !error && <tr><td colSpan={11} className="muted">Loading…</td></tr>}
            {data !== null && rows.length === 0 && <tr><td colSpan={11} className="muted">No runs yet.</td></tr>}
            {rows.map(r => (
              <tr key={r.run_id}>
                <td className="mono small nowrap">{r.run_id}</td>
                <td><div className="name">{r.integration}</div><div className="mono small muted">{r.action}</div></td>
                <td><div>{r.mode}</div><div style={{ marginTop: 4 }}><Pill kind="trigger">{r.trigger}</Pill></div></td>
                <td><Pill kind={r.status}>{r.status}</Pill></td>
                <td className="nowrap"><div>{new Date(r.started_at).toLocaleString()}</div><div className="muted small" style={{ marginTop: 2 }}>took {duration(r.duration_ms)}</div></td>
                <td>{r.pages_fetched}</td>
                <td>{r.records_pulled.toLocaleString()}</td>
                <td>{r.records_valid.toLocaleString()}</td>
                <td>{r.records_invalid ? <Pill kind="degraded">{r.records_invalid}</Pill> : 0}</td>
                <td>{r.retries}</td>
                <td className="small">
                  {r.error && (
                    // schema_drift is a warning on a run that succeeded (R-14); every other code is a failure.
                    r.error.code === 'schema_drift'
                      ? <><Pill kind="degraded">schema drift</Pill><div className="muted small" style={{ maxWidth: 280, marginTop: 4 }}>{r.error.message}</div></>
                      : <Pill kind="failed">{r.error.code}</Pill>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data && <Pager offset={offset} total={data.total} onChange={setOffset} />}
      <p className="note">Test runs are shown here but ignored by the health view.</p>
    </section>
  )
}
