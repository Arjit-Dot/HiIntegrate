import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, type Config, type IntegrationSummary, type TestResponse } from '../api/client'
import { ConfirmDialog, ErrorBox, Modal, Pill, useToast } from '../components/common'
import { Banner, Loading, Section } from '../components/modal-parts'
import { describe, messageAddsInfo } from '../lib/errors'
import { hostOf } from '../lib/config'
import { TestResult } from '../components/TestResult'
import { RunLookup } from '../components/RunLookup'
import { AlertNote } from '../components/AlertNote'

const CATEGORIES = ['identity', 'threat_intel', 'ticketing', 'alerting', 'other']
const STATUSES = ['healthy', 'degraded', 'failing', 'never_run', 'disabled']
// Plain words for the codes the API sends, so the table says what it means.
const AUTH_WORDS: Record<string, string> = { api_key: 'API key', bearer: 'Bearer token', basic: 'Username and password', oauth2_client_credentials: 'OAuth2' }
const RECORD_WORDS: Record<string, string> = { user: 'Users', device: 'Devices', alert: 'Alerts' }
const MODE_WORDS: Record<string, string> = { pull: 'Scheduled pulls', lookup: 'On-demand lookups' }

export default function Integrations() {
  const [items, setItems] = useState<IntegrationSummary[] | null>(null)
  const [all, setAll] = useState<IntegrationSummary[] | null>(null)   // the unfiltered list, for the summary tiles
  const [error, setError] = useState('')
  const [q, setQ] = useState(''); const [category, setCategory] = useState(''); const [status, setStatus] = useState(''); const [mode, setMode] = useState('')
  const [testing, setTesting] = useState<IntegrationSummary | null>(null)
  const [deleting, setDeleting] = useState<IntegrationSummary | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [running, setRunning] = useState<IntegrationSummary | null>(null)
  const toast = useToast()
  const nav = useNavigate()

  const load = useCallback(() => {
    api.listIntegrations({ q, category, status })
      .then(r => { setItems(r.items); setError('') })
      .catch(e => setError(e.message))
  }, [q, category, status])
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t) }, [load])
  useEffect(() => { api.listIntegrations({}).then(r => setAll(r.items)).catch(() => {}) }, [])

  const rows = (items ?? []).filter(i => !mode || i.actions.some(a => a.mode === mode))

  // Update the row at once and keep it. Only undo it if the call fails.
  // (A reload would bring back the old value from the Prism mock, which always returns the same list.)
  async function toggle(i: IntegrationSummary, enabled: boolean) {
    const setRow = (value: boolean) => {
      setItems(prev => prev && prev.map(x => (x.name === i.name ? { ...x, enabled: value } : x)))
      setAll(prev => prev && prev.map(x => (x.name === i.name ? { ...x, enabled: value } : x)))
    }
    setRow(enabled)
    try { await api.setEnabled(i.name, enabled); toast(`${i.display_name ?? i.name} ${enabled ? 'enabled' : 'disabled'}`) }
    catch (e) { setRow(!enabled); toast(e instanceof ApiError ? e.message : 'Could not change enabled state') }
  }

  // Deleting removes the config and its scheduling state. Records, quarantine and run history stay (they are history keyed by source).
  async function confirmDelete() {
    if (!deleting) return
    const i = deleting
    setDeleteBusy(true)
    try {
      await api.deleteIntegration(i.name)
      setItems(prev => prev && prev.filter(x => x.name !== i.name))
      setAll(prev => prev && prev.filter(x => x.name !== i.name))
      toast(`${i.display_name ?? i.name} deleted`)
      setDeleting(null)
    } catch (e) { toast(e instanceof ApiError ? e.message : 'Could not delete the integration') }
    finally { setDeleteBusy(false) }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Integrations</h1>
          <p>One row per connected tool. Health comes from the latest finished scheduled or manual run.</p>
        </div>
        <Button onClick={() => nav('/add')}>+ Add integration</Button>
      </div>
      {all && all.length > 0 && (() => {
        const state = (i: IntegrationSummary) => (i.enabled ? i.health.status : 'disabled')
        const count = (...kinds: string[]) => all.filter(i => kinds.includes(state(i))).length
        const tiles: [label: string, n: number, hint: string, tone: string][] = [
          ['Integrations', all.length, 'connected tools', 'accent'],
          ['Healthy', count('healthy'), 'last run went well', 'ok'],
          ['Needs attention', count('degraded', 'failing'), 'degraded or failing', 'warn'],
          ['Paused', count('disabled', 'never_run'), 'switched off or not run yet', 'off'],
        ]
        return (
          <div className="stats" aria-label="Summary">
            {tiles.map(([label, n, hint, tone]) => (
              <div className={`stat ${tone}`} key={label}>
                <div className="stat-n">{n}</div>
                <div className="stat-label">{label}</div>
                <div className="stat-hint">{hint}</div>
              </div>
            ))}
          </div>
        )
      })()}
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
        <table className="intable">
          <thead><tr>
            <th>Integration</th>
            <th title="The kinds of records this integration stores: users, devices or alerts">Data it collects</th>
            <th title="Pulls run on a schedule and fetch many records. Lookups run when you ask and return one record.">What it can do</th>
            <th>Last run</th>
            <th title="Judged from the latest finished scheduled or manual run">Health</th>
            <th title="Turn off to stop scheduled runs">Scheduled runs</th>
            <th><span className="sr-only">Actions</span></th>
          </tr></thead>
          <tbody>
            {items === null && !error && <tr><td colSpan={7} className="muted">Loading…</td></tr>}
            {items !== null && rows.length === 0 && <tr><td colSpan={7} className="muted">No integrations match.</td></tr>}
            {rows.map(i => {
              const h = i.health
              const status = i.enabled ? h.status : 'disabled'
              return (
                <tr key={i.name}>
                  <td>
                    <div className="name">{i.display_name ?? i.name}</div>
                    <div className="muted small mono">{i.name}</div>
                    <dl className="facts">
                      <div><dt>Category</dt><dd>{i.category}</dd></div>
                      <div><dt>Sign-in</dt><dd>{AUTH_WORDS[i.auth_type] ?? i.auth_type}</dd></div>
                    </dl>
                  </td>
                  <td><div className="pill-row">{i.schemas.length ? i.schemas.map(s => <Pill key={s} kind="schema">{RECORD_WORDS[s] ?? s}</Pill>) : <span className="muted small">Nothing yet</span>}</div></td>
                  <td>
                    {(['pull', 'lookup'] as const).map(m => {
                      const names = i.actions.filter(a => a.mode === m)
                      if (!names.length) return null
                      const shown = names.slice(0, 2), more = names.slice(2)
                      return (
                        <div className="actions-cell" key={m}>
                          <Pill kind={m}>{MODE_WORDS[m]} · {names.length}</Pill>
                          {shown.map(a => <code key={a.name}>{a.name}</code>)}
                          {more.length > 0 && <span className="muted small" title={more.map(a => a.name).join(', ')}>+{more.length} more</span>}
                        </div>
                      )
                    })}
                  </td>
                  <td><div>{h.last_run_at ? new Date(h.last_run_at).toLocaleString() : 'Not run yet'}</div><div className="muted small" style={{ marginTop: 4 }}>{(h.records_pulled ?? 0).toLocaleString()} {h.records_pulled === 1 ? 'record' : 'records'} pulled</div></td>
                  <td>
                    <Pill kind={status}>{status}</Pill>
                    {h.last_error && <div className="muted small" style={{ maxWidth: 240, marginTop: 4 }}>{h.last_error.message}</div>}
                    <AlertNote name={i.name} alert={i.alert} health={h} enabled={i.enabled} compact />
                  </td>
                  <td><Switch checked={i.enabled} onCheckedChange={v => toggle(i, v)} aria-label={`Enable ${i.name}`} /></td>
                  <td><div className="row-actions">
                    {i.actions.some(a => a.mode === 'lookup') && <><Button variant="secondary" size="sm" onClick={() => setRunning(i)}>Run</Button></>}
                    <Button variant="secondary" size="sm" onClick={() => setTesting(i)}>Test</Button>
                    <Link to={`/integrations/${encodeURIComponent(i.name)}/edit`}><Button variant="secondary" size="sm">Edit</Button></Link>
                    <Link to={`/integrations/${encodeURIComponent(i.name)}/edit?add=1`}><Button variant="secondary" size="sm" title="Add several actions to this integration at once">+ Actions</Button></Link>
                    <Button variant="destructive" size="sm" onClick={() => setDeleting(i)} title="Delete this integration's config">Delete</Button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="note"><Pill kind="pull">Scheduled pulls</Pill> run on a schedule and fetch many records. <Pill kind="lookup">On-demand lookups</Pill> run when you ask and return one record. One integration can have both.</p>
      {running && <RunLookup integ={running} onClose={() => setRunning(null)} />}
      {testing && <TestModal integ={testing} onClose={() => setTesting(null)} />}
      {deleting && (
        <ConfirmDialog title={`Delete ${deleting.display_name ?? deleting.name}?`} subtitle="This removes the integration. It cannot be undone."
          confirmLabel="Delete integration" cancelLabel="Keep it" danger busy={deleteBusy} onConfirm={confirmDelete} onCancel={() => setDeleting(null)}>
          <Section title="What will be removed">
            <ul className="bullets"><li>The config: its login settings, actions and field mapping.</li><li>Its schedule, so no more scheduled pulls.</li></ul>
          </Section>
          <Section title="What stays">
            <ul className="bullets"><li>Records it already pulled (still on the Results page).</li><li>Quarantined records.</li><li>Run history.</li></ul>
          </Section>
          <p className="field-note">To use this service again, add it as a new integration. Its secret on the Secrets page is not touched.</p>
        </ConfirmDialog>
      )}
    </section>
  )
}

function TestModal({ integ, onClose }: { integ: IntegrationSummary; onClose: () => void }) {
  const [action, setAction] = useState(integ.actions[0]?.name ?? '')
  const [config, setConfig] = useState<Config | null>(null)
  const [inputs, setInputs] = useState('')
  const [result, setResult] = useState<TestResponse | null>(null)
  const [failure, setFailure] = useState<{ code: string | null; message: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const resultRef = useRef<HTMLDivElement>(null)

  useEffect(() => { api.getIntegration(integ.name).then(r => setConfig(r.config as Config)).catch(() => setConfig(null)) }, [integ.name])
  const mode = integ.actions.find(a => a.name === action)?.mode
  const isLookup = mode === 'lookup'
  const host = config ? hostOf(String(config.base_url ?? ''), Object.entries(config.vars ?? {}).map(([k, v]) => `${k}=${v}`).join('\n')) || null : null

  // A lookup needs its inputs: start the box with one empty value per input the action declares.
  useEffect(() => {
    setResult(null); setFailure(null)
    const names = Object.keys(config?.actions?.[action]?.inputs ?? {})
    setInputs(names.length ? JSON.stringify(Object.fromEntries(names.map(n => [n, ''])), null, 2) : '{\n  "id": ""\n}')
  }, [action, config])

  let parsed: Record<string, unknown> | undefined
  let inputsError = ''
  if (isLookup) { try { parsed = JSON.parse(inputs) } catch { inputsError = 'This is not valid JSON yet. Example: { "id": "u-1" }' } }

  async function run() {
    setBusy(true); setFailure(null); setResult(null)
    try { setResult(await api.test(integ.name, action, isLookup ? parsed : undefined)) }
    catch (e) { setFailure({ code: e instanceof ApiError ? e.code : null, message: (e as Error).message }) }
    setBusy(false)
    setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50)
  }
  const failed = failure ? describe(failure.code, failure.message) : null
  return (
    <Modal title={`Test ${integ.display_name ?? integ.name}`} subtitle="Call the service once to see whether the connection and the field mapping work." onClose={onClose} size="lg"
      footer={<>
        <span className="mdl-foot-note">Reads the first page only. <b>Nothing is saved</b> and no config changes.</span>
        <Button variant="secondary" type="button" onClick={onClose}>Close</Button>
        <Button type="button" disabled={busy || !action || !!inputsError} onClick={run}>{busy ? 'Testing…' : result || failure ? 'Run test again' : 'Run test'}</Button>
      </>}>
      <Section title="What to test">
        <div className="grid">
          <div>
            <label htmlFor="test-action">Action</label>
            <select id="test-action" value={action} onChange={e => setAction(e.target.value)}>
              {integ.actions.map(a => <option key={a.name} value={a.name}>{a.name} ({a.mode === 'pull' ? 'scheduled pull' : 'on-demand lookup'})</option>)}
            </select>
            <div className="hint">{mode === 'pull' ? 'A pull fetches many records. The test reads only the first page.' : 'A lookup fetches one record, so it needs the input below.'}</div>
          </div>
          <div>
            <label>Calls</label>
            <div className="mono" style={{ padding: '11px 0' }}>{host ?? 'loading…'}</div>
            <div className="hint">The host from this integration's Base URL.</div>
          </div>
          {isLookup && (
            <div className="full">
              <label htmlFor="test-inputs" className="req">Inputs (JSON)</label>
              <textarea id="test-inputs" className="mono" value={inputs} aria-invalid={!!inputsError || undefined} onChange={e => setInputs(e.target.value)} />
              {inputsError ? <div className="hint err">{inputsError}</div> : <div className="hint">Give a value for each input, for example the id of a user to look up.</div>}
            </div>
          )}
        </div>
      </Section>
      <div ref={resultRef}>
        {busy && <Loading title={`Calling ${host ?? 'the service'}…`} hint="Reading the first page. This usually takes a second or two, and up to 30 seconds if the service is slow." />}
        {!busy && failure && (
          <Banner tone="failed" title={failed?.title ?? 'The test could not run'} next={failed?.next}>{failed?.explain} {messageAddsInfo(failure.code) && <span className="muted">({failure.message})</span>}</Banner>
        )}
        {!busy && result && <TestResult r={result} integration={integ.display_name ?? integ.name} action={action} host={host} />}
      </div>
    </Modal>
  )
}
