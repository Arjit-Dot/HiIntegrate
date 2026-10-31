import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { api, ApiError, type Config, type IntegrationSummary } from '../api/client'
import { ErrorBox, Modal, Pill } from './common'

type InputDef = { type: string; required?: boolean; values?: string[] }
type Outcome =
  | { kind: 'ok'; record: Record<string, unknown>; runId: string | null }
  | { kind: 'rejected'; message: string; details: unknown }
  | { kind: 'failed'; message: string; runId?: string; errorCode?: string }
  | { kind: 'error'; message: string }

/** Pick a lookup action, fill its inputs, see the mapped record (D-10: the lookup is recorded as a manual run). */
export function RunLookup({ integ, onClose }: { integ: IntegrationSummary; onClose: () => void }) {
  const lookups = integ.actions.filter(a => a.mode === 'lookup')
  const [config, setConfig] = useState<Config | null>(null)
  const [loadError, setLoadError] = useState('')
  const [action, setAction] = useState(lookups[0]?.name ?? '')
  const [values, setValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState<Outcome | null>(null)

  useEffect(() => { api.getIntegration(integ.name).then(r => setConfig(r.config as Config)).catch(e => setLoadError(e.message)) }, [integ.name])
  useEffect(() => { setValues({}); setOut(null) }, [action])

  const act = config?.actions?.[action]
  const defs: Record<string, InputDef> = act?.inputs ?? {}
  const missing = Object.entries(defs).filter(([k, d]) => d.required !== false && !values[k]?.trim()).map(([k]) => k)
  const schema: string | undefined = act?.target_schema

  async function run() {
    const inputs: Record<string, unknown> = {}
    for (const [k, d] of Object.entries(defs)) {
      const v = values[k]?.trim()
      if (!v) continue
      inputs[k] = d.type === 'int' && /^-?\d+$/.test(v) ? Number(v) : v
    }
    setBusy(true); setOut(null)
    try {
      const r = await api.runAction(integ.name, action, inputs)
      setOut({ kind: 'ok', record: r.body, runId: r.runId })
    } catch (e) {
      if (!(e instanceof ApiError)) setOut({ kind: 'error', message: (e as Error).message })
      else if (e.status === 400) setOut({ kind: 'rejected', message: e.message, details: e.details })
      else if (e.code === 'run_failed') {
        const d = (e.details ?? {}) as { run_id?: string; error_code?: string }
        setOut({ kind: 'failed', message: e.message, runId: d.run_id, errorCode: d.error_code })
      } else setOut({ kind: 'error', message: e.status === 409 ? 'This action is already running. Try again in a moment.' : e.message })
    }
    setBusy(false)
  }

  return (
    <Modal title={`Run a lookup: ${integ.display_name ?? integ.name}`} onClose={onClose}>
      {loadError && <ErrorBox message={loadError} />}
      <div style={{ marginBottom: 12 }}>
        <label className="req">Action</label>
        <select value={action} onChange={e => setAction(e.target.value)}>{lookups.map(l => <option key={l.name}>{l.name}</option>)}</select>
        <div className="hint">Only lookup actions are listed. Pulls run on a schedule.</div>
      </div>
      {config === null && !loadError && <div className="muted">Loading inputs…</div>}
      {Object.entries(defs).map(([k, d]) => (
        <div style={{ marginBottom: 12 }} key={k}>
          <label className={d.required !== false ? 'req' : ''}>{k} <span className="muted" style={{ fontWeight: 400 }}>({d.type})</span></label>
          {d.type === 'enum'
            ? <select value={values[k] ?? ''} onChange={e => setValues(p => ({ ...p, [k]: e.target.value }))}><option value="">Choose…</option>{(d.values ?? []).map(v => <option key={v}>{v}</option>)}</select>
            : <input type="text" className="mono" placeholder={d.type} value={values[k] ?? ''} onChange={e => setValues(p => ({ ...p, [k]: e.target.value }))} />}
        </div>
      ))}
      {act && <div className="muted small" style={{ marginBottom: 12 }}>Fills the <b>{schema}</b> schema. {act.store === false ? <>Result is <b>not saved</b> (<code>store: false</code>).</> : <>Result is <b>saved</b>; running it again updates the record.</>}</div>}
      <div className="actions-bar">
        <Button disabled={busy || !act || missing.length > 0} onClick={run}>{busy ? 'Running…' : 'Run lookup'}</Button>
        {missing.length > 0 && <span className="muted small">Still needed: {missing.join(', ')}</span>}
      </div>
      <div className="runbox">
        {out?.kind === 'ok' && <>
          <div style={{ marginBottom: 10 }}><Pill kind="success">success</Pill> <Pill kind="trigger">manual</Pill></div>
          <h3 style={{ marginBottom: 6 }}>Mapped record</h3>
          <pre>{JSON.stringify(out.record, null, 2)}</pre>
          {out.runId && <div className="hint" style={{ marginTop: 8 }}>Recorded as <b>{out.runId}</b> in <Link to="/runs" onClick={onClose}>Run history</Link>.</div>}
        </>}
        {out?.kind === 'rejected' && <div className="issue"><div>
          <b>Rejected before any request was sent.</b> No run was created.
          <div>{out.message}</div>
          {out.details != null && <pre style={{ marginTop: 8 }}>{JSON.stringify(out.details, null, 2)}</pre>}
        </div></div>}
        {out?.kind === 'failed' && <>
          <div style={{ marginBottom: 10 }}><Pill kind="failed">failed</Pill> {out.errorCode && <Pill kind="trigger">{out.errorCode}</Pill>}</div>
          <ErrorBox message={out.message} />
          {out.runId && <div className="hint" style={{ marginTop: 8 }}>Recorded as <b>{out.runId}</b> in <Link to="/runs" onClick={onClose}>Run history</Link>.</div>}
        </>}
        {out?.kind === 'error' && <ErrorBox message={out.message} />}
      </div>
    </Modal>
  )
}
