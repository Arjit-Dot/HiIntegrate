import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { api, ApiError, type Config, type IntegrationSummary } from '../api/client'
import { ErrorBox, Modal } from './common'
import { Banner, KeyValue, Loading, RecordTable, Section, TechDetails } from './modal-parts'
import { describe } from '../lib/errors'

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

  const inputEntries = Object.entries(defs)
  const failedInfo = out?.kind === 'failed' ? describe(out.errorCode, out.message) : null
  return (
    <Modal title={`Look up one record: ${integ.display_name ?? integ.name}`} subtitle="Ask the service for a single record on demand, for example one user by id." onClose={onClose} size="lg"
      footer={<>
        <span className="mdl-foot-note">{act?.store === false ? <>The result is <b>shown only</b>, not stored.</> : <>The record is <b>saved</b>. Running it again updates it.</>} The run is logged in Run history.</span>
        <Button variant="secondary" type="button" onClick={onClose}>Close</Button>
        <Button type="button" disabled={busy || !act || missing.length > 0} onClick={run}>{busy ? 'Looking up…' : out ? 'Look up again' : 'Look up record'}</Button>
      </>}>
      {loadError && <ErrorBox message={loadError} />}
      <Section title="What to look up">
        <div className="grid">
          <div className="full">
            <label htmlFor="lookup-action" className="req">Lookup action</label>
            <select id="lookup-action" value={action} onChange={e => setAction(e.target.value)}>{lookups.map(l => <option key={l.name}>{l.name}</option>)}</select>
            <div className="hint">Only lookups are listed here. Pulls run on a schedule.{schema && <> This one fills the <b>{schema}</b> schema.</>}</div>
          </div>
          {config === null && !loadError && <div className="full"><Loading title="Loading this action's inputs…" /></div>}
          {inputEntries.map(([k, d]) => (
            <div key={k} className={inputEntries.length === 1 ? 'full' : undefined}>
              <label htmlFor={`in-${k}`} className={d.required !== false ? 'req' : ''}>{k}</label>
              {d.type === 'enum'
                ? <select id={`in-${k}`} value={values[k] ?? ''} onChange={e => setValues(p => ({ ...p, [k]: e.target.value }))}><option value="">Choose…</option>{(d.values ?? []).map(v => <option key={v}>{v}</option>)}</select>
                : <input id={`in-${k}`} type="text" className="mono" placeholder={d.type === 'int' ? 'for example 42' : 'for example u-1'} value={values[k] ?? ''} onChange={e => setValues(p => ({ ...p, [k]: e.target.value }))} />}
              <div className="hint">{d.required !== false ? 'Required' : 'Optional'}, {d.type === 'enum' ? 'pick one of the values' : `a ${d.type}`}.{missing.includes(k) && <> <span className="err">Fill this in to continue.</span></>}</div>
            </div>
          ))}
        </div>
      </Section>

      <div className="runbox" style={{ marginTop: 0 }}>
        {busy && <Loading title="Asking the service…" hint="This usually takes a second or two." />}
        {!busy && out?.kind === 'ok' && (
          <div className="mdl-stack">
            <Banner tone="success" title="Record found">The service returned it, and it was mapped to the {schema ?? 'common'} schema.</Banner>
            <Section title="The record"><RecordTable record={out.record} /></Section>
            <KeyValue rows={[['Run', out.runId ? <>{out.runId} · <Link to="/runs" onClick={onClose}>see Run history</Link></> : null]]} />
            <TechDetails data={out.record} title="Technical details (raw mapped record)" />
          </div>
        )}
        {!busy && out?.kind === 'rejected' && (
          <div className="mdl-stack">
            <Banner tone="warning" title="Check the inputs" next="Fix the value(s) and look up again. No request was sent, and no run was created.">{out.message}</Banner>
            {out.details != null && <TechDetails data={out.details} />}
          </div>
        )}
        {!busy && out?.kind === 'failed' && (
          <div className="mdl-stack">
            <Banner tone="failed" title={failedInfo?.title ?? 'The lookup failed'} next={failedInfo?.next}>{failedInfo?.explain}</Banner>
            <KeyValue rows={[['Error code', out.errorCode ? <code>{out.errorCode}</code> : null], ['Run', out.runId ? <>{out.runId} · <Link to="/runs" onClick={onClose}>see Run history</Link></> : null]]} />
            <TechDetails text={out.message} />
          </div>
        )}
        {!busy && out?.kind === 'error' && <ErrorBox message={out.message} />}
      </div>
    </Modal>
  )
}
