import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, type IntegrationSummary, type TestResponse } from '../api/client'
import { ErrorBox, Modal, Pill, useToast } from '../components/ui'
import { TestResult } from '../components/TestResult'

const CATEGORIES = ['identity', 'threat_intel', 'ticketing', 'alerting', 'other']
const STATUSES = ['healthy', 'degraded', 'failing', 'never_run', 'disabled']

export default function Integrations() {
  const [items, setItems] = useState<IntegrationSummary[] | null>(null)
  const [error, setError] = useState('')
  const [q, setQ] = useState(''); const [category, setCategory] = useState(''); const [status, setStatus] = useState(''); const [mode, setMode] = useState('')
  const [testing, setTesting] = useState<IntegrationSummary | null>(null)
  const toast = useToast()
  const nav = useNavigate()

  const load = useCallback(() => {
    api.listIntegrations({ q, category, status })
      .then(r => { setItems(r.items); setError('') })
      .catch(e => setError(e.message))
  }, [q, category, status])
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t) }, [load])

  const rows = (items ?? []).filter(i => !mode || i.actions.some(a => a.mode === mode))

  async function toggle(i: IntegrationSummary, enabled: boolean) {
    try { await api.setEnabled(i.name, enabled); toast(`${i.display_name ?? i.name} ${enabled ? 'enabled' : 'disabled'}`); load() }
    catch (e) { toast(e instanceof ApiError ? e.message : 'Could not change enabled state') }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Integrations</h1>
          <p>One row per connected tool. Health comes from the latest finished scheduled or manual run.</p>
        </div>
        <button className="btn" onClick={() => nav('/add')}>+ Add integration</button>
      </div>
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <input type="text" placeholder="Search by name" value={q} onChange={e => setQ(e.target.value)} />
        <select value={category} onChange={e => setCategory(e.target.value)}>
          <option value="">All categories</option>{CATEGORIES.map(c => <option key={c}>{c}</option>)}
        </select>
        <select value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">All statuses</option>{STATUSES.map(c => <option key={c}>{c}</option>)}
        </select>
        <select value={mode} onChange={e => setMode(e.target.value)}>
          <option value="">All action types</option><option value="pull">Has pull actions</option><option value="lookup">Has lookup actions</option>
        </select>
      </div>
      {error && <ErrorBox message={error} />}
      <div className="card tablewrap">
        <table>
          <thead><tr><th>Integration</th><th>Category</th><th>Auth</th><th>Fills</th><th>Actions</th><th>Last run</th><th>Records</th><th>Health</th><th>Enabled</th><th></th></tr></thead>
          <tbody>
            {items === null && !error && <tr><td colSpan={10} className="muted">Loading…</td></tr>}
            {items !== null && rows.length === 0 && <tr><td colSpan={10} className="muted">No integrations match.</td></tr>}
            {rows.map(i => {
              const h = i.health
              const status = i.enabled ? h.status : 'disabled'
              return (
                <tr key={i.name}>
                  <td><div className="name">{i.display_name ?? i.name}</div><div className="muted small mono">{i.name}</div></td>
                  <td>{i.category}</td>
                  <td className="mono small">{i.auth_type}</td>
                  <td>{i.schemas.map(s => <Pill key={s} kind="schema">{s}</Pill>)}</td>
                  <td>
                    {(['pull', 'lookup'] as const).map(m => {
                      const names = i.actions.filter(a => a.mode === m)
                      return names.length ? <div className="small" style={{ marginBottom: 4 }} key={m}><Pill kind={m}>{m}</Pill> {names.map(a => <code key={a.name}>{a.name} </code>)}</div> : null
                    })}
                  </td>
                  <td className="small">{h.last_run_at ? new Date(h.last_run_at).toLocaleString() : 'never'}</td>
                  <td>{(h.records_pulled ?? 0).toLocaleString()}</td>
                  <td>
                    <Pill kind={status}>{status}</Pill>
                    {h.last_error && <div className="muted small" style={{ maxWidth: 240, marginTop: 4 }}>{h.last_error.message}</div>}
                  </td>
                  <td><label className="switch"><input type="checkbox" checked={i.enabled} onChange={e => toggle(i, e.target.checked)} /><span className="slider" /></label></td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button className="btn secondary small" onClick={() => setTesting(i)}>Test</button>{' '}
                    <Link to={`/integrations/${encodeURIComponent(i.name)}/edit`}><button className="btn secondary small">Edit</button></Link>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="note"><Pill kind="pull">pull</Pill> runs on a schedule and fetches many records. <Pill kind="lookup">lookup</Pill> runs on demand and returns one record. One integration can have both.</p>
      {testing && <TestModal integ={testing} onClose={() => setTesting(null)} />}
    </section>
  )
}

function TestModal({ integ, onClose }: { integ: IntegrationSummary; onClose: () => void }) {
  const [action, setAction] = useState(integ.actions[0]?.name ?? '')
  const [inputs, setInputs] = useState('{\n  "id": "1"\n}')
  const [result, setResult] = useState<TestResponse | null>(null)
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const isLookup = integ.actions.find(a => a.name === action)?.mode === 'lookup'

  async function run() {
    setBusy(true); setError(''); setResult(null)
    try { setResult(await api.test(integ.name, action, isLookup ? JSON.parse(inputs) : undefined)) }
    catch (e) { setError(e instanceof SyntaxError ? 'Inputs must be valid JSON.' : (e as Error).message) }
    setBusy(false)
  }
  return (
    <Modal title={`Test ${integ.display_name ?? integ.name}`} onClose={onClose}>
      <div className="grid">
        <div><label>Action</label><select value={action} onChange={e => setAction(e.target.value)}>{integ.actions.map(a => <option key={a.name} value={a.name}>{a.name} ({a.mode})</option>)}</select></div>
        {isLookup && <div className="full"><label>Inputs (JSON)</label><textarea className="mono" value={inputs} onChange={e => setInputs(e.target.value)} /></div>}
      </div>
      <div className="actions-bar" style={{ marginTop: 14 }}><button className="btn" disabled={busy || !action} onClick={run}>{busy ? 'Testing…' : 'Run test (first page only)'}</button></div>
      {error && <ErrorBox message={error} />}
      {result && <TestResult r={result} />}
    </Modal>
  )
}
