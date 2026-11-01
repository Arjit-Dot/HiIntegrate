import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, ApiError, type Config, type ProposeFixResponse, type QuarantineRecord, type RunRecord } from '../api/client'
import { Modal, useToast } from './common'
import { Banner, KeyValue, Loading, RecordTable, Section, TechDetails } from './modal-parts'
import { describe, messageAddsInfo, REASON_INFO } from '../lib/errors'

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
  const [errorCode, setErrorCode] = useState<string | null>(null)
  const [reasons, setReasons] = useState<QuarantineRecord[] | null>(null)   // the quarantined records of this action, to say what went wrong
  const [off, setOff] = useState(false)
  const [fix, setFix] = useState<ProposeFixResponse | null>(null)
  const [revision, setRevision] = useState<number | null>(null)   // the revision the proposal was made against
  const [applying, setApplying] = useState(false)
  const [applied, setApplied] = useState(false)
  const [savedAt, setSavedAt] = useState<string | null>(null)   // set when the proposal on screen is the saved one
  const [running, setRunning] = useState(false)
  const [after, setAfter] = useState<RunRecord | null>(null)   // the run started after applying, to show the effect

  async function ask() {
    setBusy(true); setError(''); setErrorCode(null); setFix(null); setApplied(false); setSavedAt(null)
    api.listQuarantine({ source: integration, limit: 200 }).then(r => setReasons(r.items.filter(q => q.action === action))).catch(() => setReasons(null))
    try {
      const current = await api.getIntegration(integration)
      setRevision(current.revision ?? null)
      const proposal = await api.proposeFix({ kind: 'quarantine', integration, action })
      setFix(proposal)
      try { localStorage.setItem(fixKey(integration, action), JSON.stringify({ fix: proposal, revision: current.revision ?? null, at: new Date().toISOString() })) } catch { /* private mode */ }
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setOff(true)
      else {
        setError((e as Error).message); setErrorCode(e instanceof ApiError ? e.code : null)
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
        setError('This integration was edited after the proposal was made, so applying it would overwrite that edit. Ask the AI again.'); setErrorCode(null)
        return
      }
      await api.replace(integration, fix.proposed_config as Config)
      setApplied(true)
      toast(`Applied to ${integration}`)
      onApplied()
    } catch (e) { setError((e as Error).message); setErrorCode(e instanceof ApiError ? e.code : null) }
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
  const failedInfo = error ? describe(errorCode, error) : null
  // How many records failed and why, grouped, in plain words.
  const groups = (() => {
    const m = new Map<string, { reason: string; field: string; n: number }>()
    for (const q of reasons ?? []) { const k = `${q.reason}|${q.field}`; m.set(k, { reason: q.reason, field: q.field ?? '', n: (m.get(k)?.n ?? 0) + 1 }) }
    return [...m.values()].sort((x, y) => y.n - x.n)
  })()

  const footer = applied
    ? <>
        <span className="mdl-foot-note">The new config is saved. Records already quarantined stay as they are.</span>
        <Button variant="secondary" type="button" onClick={onClose}>Close</Button>
        <Button type="button" onClick={runNow} disabled={running}>{running ? 'Running…' : `Run ${action} now`}</Button>
      </>
    : <>
        <span className="mdl-foot-note">{canApply ? <><b>Nothing is saved until you press Apply fix.</b> It updates {integration} in place.</> : 'Nothing was changed.'}</span>
        <Button variant="secondary" type="button" onClick={onClose}>Discard</Button>
        <Button type="button" onClick={apply} disabled={!canApply || applying} title={canApply ? `Replace the config of ${integration} with the proposal` : 'There is nothing valid to apply'}>
          {applying ? 'Applying…' : 'Apply fix'}
        </Button>
      </>

  return (
    <Modal title={`Fix with AI: ${integration} · ${action}`} subtitle="The AI reads the records that were set aside and proposes a change to the mapping. You see the effect before anything is saved." onClose={onClose} size="lg" footer={footer}>
      {off && <Banner tone="info" title="AI is switched off">The server has no <code>LLM_API_KEY</code>. Quarantine works without it: export the records and fix the mapping by hand in Edit.</Banner>}

      {busy && <Loading title="Asking Gemini to propose a fix…" hint="It reads the quarantined records and the config, then each proposal is checked against your stored records. This can take about 10 seconds, up to a minute if the AI is busy." />}

      {!busy && error && (
        <Banner tone="failed" title={failedInfo?.title ?? 'The AI could not give a proposal'} next={fix ? 'You can still look at the saved proposal below, or ask again.' : failedInfo?.next}>
          {failedInfo?.explain} {messageAddsInfo(errorCode) && <span className="muted">({error})</span>}
          {!applied && <div style={{ marginTop: 10 }}><Button variant="secondary" size="sm" type="button" onClick={ask}>Ask again</Button></div>}
        </Banner>
      )}

      {fix && (
        <>
          {savedAt && <Banner tone="warning" title="Showing a saved proposal">From {new Date(savedAt).toLocaleString()}. It is shown because the AI could not be reached. It can only be applied if {integration} has not been edited since.</Banner>}

          {applied && <Banner tone="success" title="Fix applied" next={<>Run <code>{action}</code> again and the new run uses the fix. <Link to={`/integrations/${encodeURIComponent(integration)}/edit`}>See the new config</Link>.</>}>
            {integration} now has the updated config.
          </Banner>}
          {after && (
            <Banner tone={after.status === 'success' && after.records_invalid === 0 ? 'success' : 'warning'}
              title={after.status === 'success' ? 'The new run finished' : 'The new run failed'}>
              {after.records_valid} record{after.records_valid === 1 ? '' : 's'} saved, <b>{after.records_invalid} quarantined</b>{after.status === 'failed' && after.error ? <> ({after.error.message})</> : null}. See it in <Link to="/runs">Run history</Link>.
            </Banner>
          )}

          {fix.errors.length > 0 && (
            <Banner tone="warning" title="This proposal is not valid, so it cannot be applied" next="Ask again, or fix the mapping by hand in Edit.">
              <ul className="bullets">{fix.errors.map((e, i) => <li key={i}><code>{e.path}</code>: {e.message}</li>)}</ul>
            </Banner>
          )}

          <Section title="What went wrong" hint="The records that were set aside for this action.">
            <KeyValue rows={[['Quarantined records', reasons ? reasons.length : v ? v.checked : null]]} />
            {groups.length > 0 && (
              <ul className="bullets">
                {groups.map(g => (
                  <li key={g.reason + g.field}><b>{g.n}</b> · {REASON_INFO[g.reason]?.title ?? g.reason}{g.field ? <> (field <code>{g.field}</code>)</> : null}</li>
                ))}
              </ul>
            )}
          </Section>


          {v && (
            <Section title="What this would fix" hint="A dry run on the stored originals. Nothing was saved.">
              <div style={{ fontSize: 17 }}><b>Rescues {v.rescued} of {v.checked}</b> quarantined record{v.checked === 1 ? '' : 's'}</div>
              <div className="meter" aria-hidden><div style={{ width: `${v.checked ? Math.round((v.rescued / v.checked) * 100) : 0}%` }} /></div>
              {v.still_quarantined === 0
                ? <p className="field-note" style={{ marginTop: 0 }}>None would stay quarantined.</p>
                : <p className="field-note" style={{ marginTop: 0 }}><b>{v.still_quarantined}</b> would stay quarantined. A config change cannot repair those: a record with no id has nothing to store, and a value that is simply wrong stays wrong. This fix is partial.</p>}
              {rescuesNone && <Banner tone="warning" title="This change would not help" next="Ask the AI again (it can answer differently each time), or fix the mapping by hand.">
                The dry run rescues none of the records, so applying it would change the config without improving anything.
                <div style={{ marginTop: 10 }}><Button type="button" variant="secondary" size="sm" onClick={ask} disabled={busy}>Ask again</Button></div>
              </Banner>}
            </Section>
          )}

          {fix.changes.length === 0
            ? <Banner tone="info" title="The AI found no config change that would help">The records stay quarantined and nothing was changed. You can fix the mapping by hand in Edit.</Banner>
            : fix.changes.map(c => (
              <Section key={c.path} title="Proposed change" hint={c.reason || undefined}>
                <div className="mono small" style={{ marginBottom: 8 }}><b>{c.path}</b></div>
                <div className="diff">
                  <div className="was"><h4>Now</h4><pre>{show(c.before)}</pre></div>
                  <div className="will"><h4>After the fix</h4><pre>{show(c.after)}</pre></div>
                </div>
              </Section>
            ))}

          <details className="tech">
            <summary>Why the AI suggests this</summary>
            <div className="tech-body"><p style={{ margin: 0, lineHeight: 1.65 }}>{fix.summary}</p></div>
          </details>

          {v && v.mapped_samples.length > 0 && (
            <Section title="How a rescued record would be saved">
              <RecordTable record={v.mapped_samples[0] as Record<string, unknown>} />
            </Section>
          )}

          <TechDetails data={{ summary: fix.summary, changes: fix.changes, errors: fix.errors, verification: fix.verification, saved_at: savedAt }} />
        </>
      )}
    </Modal>
  )
}
