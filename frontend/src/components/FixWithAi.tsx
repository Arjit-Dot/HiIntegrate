import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, ApiError, type Config, type ProposeFixResponse, type RunRecord } from '../api/client'
import { Modal, Pill, useToast } from './common'

// "Fix with AI" on the Quarantine page (D-14). The server asks the model for a change, validates it, and maps the stored
// raw records again with it (a dry run): "rescues N of M". Nothing is saved by that. Apply is the normal
// PUT /integrations/{id}, pressed by a person who has seen the change and the count.

// The last good proposal per action is kept in this browser as a demo fallback. It can only be applied if the integration still
// has the revision it was made for, which is the same guard as for a fresh proposal.
type SavedFix = { fix: ProposeFixResponse; revision: number | null; at: string }
const fixKey = (integration: string, action: string) => `hiintegrate.fix.${integration}.${action}`
function loadFix(integration: string, action: string): SavedFix | null {
  try { return JSON.parse(localStorage.getItem(fixKey(integration, action)) ?? 'null') } catch { return null }
}

const show = (v: unknown) => (v === undefined || v === null ? 'new' : JSON.stringify(v, null, 2))

type Props = { integration: string; action: string; onClose: () => void; onApplied: () => void }

export function FixWithAi({ integration, action, onClose, onApplied }: Props) {
  const toast = useToast()
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [off, setOff] = useState(false)
  const [fix, setFix] = useState<ProposeFixResponse | null>(null)
  const [revision, setRevision] = useState<number | null>(null)   // the revision the proposal was made against
  const [applying, setApplying] = useState(false)
  const [applied, setApplied] = useState(false)
  const [savedAt, setSavedAt] = useState<string | null>(null)   // set when the proposal on screen is the saved one
  const [running, setRunning] = useState(false)
  const [after, setAfter] = useState<RunRecord | null>(null)   // the run started after applying, to show the effect

  async function ask() {
    setBusy(true); setError(''); setFix(null); setApplied(false); setSavedAt(null)
    try {
      const current = await api.getIntegration(integration)
      setRevision(current.revision ?? null)
      const proposal = await api.proposeFix({ kind: 'quarantine', integration, action })
      setFix(proposal)
      try { localStorage.setItem(fixKey(integration, action), JSON.stringify({ fix: proposal, revision: current.revision ?? null, at: new Date().toISOString() })) } catch { /* private mode */ }
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setOff(true)
      else {
        setError((e as Error).message)
        const saved = loadFix(integration, action)
        if (saved) { setFix(saved.fix); setRevision(saved.revision); setSavedAt(saved.at) }
      }
    } finally { setBusy(false) }
  }
  // Ask once per opening. (In development React runs effects twice: without this the model would be called twice.)
  const asked = useRef('')
  useEffect(() => {
    if (asked.current === `${integration}.${action}`) return
    asked.current = `${integration}.${action}`
    ask()
  }, [integration, action])   // eslint-disable-line react-hooks/exhaustive-deps

  const rescuesNone = !!fix?.verification && fix.verification.rescued === 0   // the dry run says it would help no record
  const canApply = !!fix && fix.changes.length > 0 && fix.errors.length === 0 && !!fix.proposed_config && !applied && !rescuesNone

  async function apply() {
    if (!fix?.proposed_config) return
    setApplying(true); setError('')
    try {
      // The proposal replaces the whole config, so refuse if someone edited the integration after it was made.
      const now = await api.getIntegration(integration)
      if (revision !== null && now.revision !== revision) {
        setError('This integration was edited after the proposal was made, so applying it would overwrite that edit. Ask the AI again.')
        return
      }
      await api.replace(integration, fix.proposed_config as Config)
      setApplied(true)
      toast(`Applied to ${integration}`)
      onApplied()
    } catch (e) { setError((e as Error).message) }
    finally { setApplying(false) }
  }

  async function runNow() {
    setRunning(true); setAfter(null)
    try {
      const r = await api.runAction(integration, action)
      if (!r.runId) { toast(`Started ${action}`); return }
      // A pull runs in the background: look at it until it finishes (up to about 30 seconds).
      for (let i = 0; i < 30; i++) {
        const latest = (await api.listRuns({ integration, limit: 5 })).items.find(x => (x as RunRecord & { run_id?: string }).run_id === r.runId)
        if (latest && latest.status !== 'running') { setAfter(latest); return }
        await new Promise(res => setTimeout(res, 1000))
      }
      toast(`${action} is still running. Check the Runs page.`)
    } catch (e) { toast((e as Error).message) }
    finally { setRunning(false); onApplied() }
  }

  const v = fix?.verification
  return (
    <Modal title={`Fix with AI: ${integration}.${action}`} onClose={onClose}>
      {off && <div className="callout"><strong>AI is switched off.</strong> The server has no <code>LLM_API_KEY</code>. Quarantine works without it: export the records and fix the mapping by hand in Edit.</div>}
      {busy && <p className="muted"><Sparkles size={14} style={{ verticalAlign: -2 }} /> Reading the quarantined records and the config, then checking the AI's proposal against them. This can take up to a minute.</p>}
      {error && <div className="hint err" role="alert">{error}{!applied && !busy && <> <Button variant="secondary" size="sm" type="button" onClick={ask}>Ask again</Button></>}</div>}

      {fix && (
        <>
          {savedAt && <div className="callout">This is the <b>saved proposal from {new Date(savedAt).toLocaleString()}</b>, shown because the AI could not be reached. You can only apply it if {integration} has not been edited since.</div>}
          <p style={{ marginTop: 0 }}>{fix.summary}</p>

          {fix.changes.length === 0 && (
            <div className="callout">The AI found no config change that fixes this. The records stay quarantined; nothing was changed.</div>
          )}

          {fix.changes.map(c => (
            <div key={c.path} style={{ marginBottom: 14 }}>
              <div className="mono small"><b>{c.path}</b></div>
              <div className="muted small" style={{ margin: '2px 0 6px' }}>{c.reason}</div>
              <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div><div className="hint">Now</div><pre>{show(c.before)}</pre></div>
                <div><div className="hint">Proposed</div><pre>{show(c.after)}</pre></div>
              </div>
            </div>
          ))}

          {fix.errors.length > 0 && (
            <div className="callout" role="alert">
              <strong>This proposal is not valid, so it cannot be applied.</strong>
              <ul>{fix.errors.map((e, i) => <li key={i}><code>{e.path}</code>: {e.message}</li>)}</ul>
            </div>
          )}

          {v && (
            <div className="callout">
              <div><b>Rescues {v.rescued} of {v.checked}</b> quarantined record{v.checked === 1 ? '' : 's'} <span className="muted">(a dry run on the stored originals: nothing was saved)</span></div>
              <div style={{ margin: '8px 0', height: 8, borderRadius: 4, background: 'var(--border, #e5e7eb)', overflow: 'hidden' }} aria-hidden>
                <div style={{ width: `${v.checked ? Math.round((v.rescued / v.checked) * 100) : 0}%`, height: '100%', background: 'var(--ok, #16a34a)' }} />
              </div>
              <div className="small">{v.still_quarantined === 0 ? 'None would stay quarantined.' : <>{v.still_quarantined} would <Pill kind="failed">still be quarantined</Pill>, so this fix is partial.</>}</div>
              {v.mapped_samples.length > 0 && <details style={{ marginTop: 8 }} open><summary>How {v.mapped_samples.length} of them would be saved</summary><pre style={{ marginTop: 6 }}>{JSON.stringify(v.mapped_samples, null, 2)}</pre></details>}
            </div>
          )}

          {applied ? (
            <div className="callout">
              <b>Applied.</b> {integration} now has the new config (it was updated in place; <Link to={`/integrations/${encodeURIComponent(integration)}/edit`}>see it in Edit</Link>).
              Records already quarantined stay as they are. Run <code>{action}</code> again and the new run uses the fix.
              <div style={{ marginTop: 8 }}><Button type="button" size="sm" onClick={runNow} disabled={running}>{running ? 'Running…' : `Run ${action} now`}</Button></div>
              {after && (
                <div style={{ marginTop: 8 }} role="status">
                  <b>{after.status === 'success' ? 'Run finished' : 'Run failed'}:</b> {after.records_valid} saved, <b>{after.records_invalid} quarantined</b>
                  {after.status === 'failed' && after.error ? <> ({after.error.message})</> : null}. <span className="muted">See it on the <Link to="/runs">Runs</Link> page.</span>
                </div>
              )}
            </div>
          ) : (
            <div className="inline" style={{ justifyContent: 'flex-end' }}>
              <Button variant="secondary" type="button" onClick={onClose}>Close without applying</Button>
              <Button type="button" onClick={apply} disabled={!canApply || applying} title={canApply ? 'Replace the config with the proposal' : 'There is nothing valid to apply'}>
                {applying ? 'Applying…' : 'Apply this change'}
              </Button>
            </div>
          )}
          {!applied && rescuesNone && <div className="hint err" style={{ textAlign: 'right', marginTop: 6 }}>Not applied: the dry run shows this change rescues none of the quarantined records, so it would change the config without helping. Ask again, or fix it by hand.</div>}
          {!applied && canApply && <div className="hint" style={{ textAlign: 'right', marginTop: 6 }}>Apply updates {integration} in place. Nothing changes until you press it.</div>}
        </>
      )}
    </Modal>
  )
}
