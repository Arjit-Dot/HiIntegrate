import type { TestResponse } from '../api/client'
import { Pill } from './ui'

// B-3: raw reply beside the mapped record, with the paths that were not found highlighted.
export function TestResult({ r }: { r: TestResponse }) {
  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Pill kind={r.ok ? 'success' : 'failed'}>{r.status_code ? `HTTP ${r.status_code}` : r.ok ? 'OK' : 'Failed'}</Pill>{' '}
        {r.latency_ms != null && <Pill kind="trigger">{r.latency_ms} ms</Pill>}{' '}
        <Pill kind="trigger">{r.pages_fetched} page{r.pages_fetched === 1 ? '' : 's'} fetched</Pill>
      </div>
      {r.missing_paths.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div className="hint" style={{ marginBottom: 6 }}>Paths not found in the reply:</div>
          {r.missing_paths.map(p => <span className="missing" key={p}>{p}</span>)}
        </div>
      )}
      {r.notes.map((n, i) => <div className="hint" key={i}>{n}</div>)}
      <div className="two" style={{ marginTop: 10 }}>
        <div><h3>Raw reply</h3><pre>{JSON.stringify(r.raw_sample, null, 2)}</pre></div>
        <div><h3>Mapped record</h3><pre>{JSON.stringify(r.mapped_sample, null, 2)}</pre></div>
      </div>
    </div>
  )
}
