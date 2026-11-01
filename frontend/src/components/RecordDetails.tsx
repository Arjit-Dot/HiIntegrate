import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import type { QuarantineRecord, RunRecord } from '../api/client'
import { describe, messageAddsInfo, REASON_INFO } from '../lib/errors'
import { Modal } from './common'
import { Banner, KeyValue, RecordTable, Section, TechDetails } from './modal-parts'

const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : null)

/** One quarantined record: why it was set aside first, the failing field, then the original record. */
export function QuarantineDetail({ q, onClose }: { q: QuarantineRecord; onClose: () => void }) {
  const info = REASON_INFO[q.reason]
  const raw = q.raw && typeof q.raw === 'object' && !Array.isArray(q.raw) ? (q.raw as Record<string, unknown>) : null
  return (
    <Modal title="Quarantined record" subtitle={`Set aside during ${q.run_id} of ${q.source} · ${q.action}. The run carried on without it.`} onClose={onClose} size="lg"
      footer={<>
        <span className="mdl-foot-note">The original is kept untouched, so a fixed mapping can be tried on it again.</span>
        <Button type="button" onClick={onClose}>Close</Button>
      </>}>
      <Banner tone="warning" title={info?.title ?? q.reason}
        next={<>{info?.fixable ?? 'Check the mapping for this field.'} On the Quarantine page, <b>Fix with AI</b> can propose a change.</>}>
        {info?.explain ?? 'This record did not pass the rules.'} {q.field && <>The field that failed is <code>{q.field}</code>.</>}
      </Banner>
      <Section title="Where it came from">
        <KeyValue rows={[['Integration', q.source], ['Action', <code key="a">{q.action}</code>], ['Run', <Link key="r" to="/runs" onClick={onClose}>{q.run_id}</Link>], ['Record type', q.target_schema], ['Failing field', q.field ? <code key="f">{q.field}</code> : null], ['Set aside at', when(q.created_at)]]} />
      </Section>
      <Section title="The original record" hint="Exactly as the service sent it.">
        {raw ? <RecordTable record={raw} /> : <pre>{JSON.stringify(q.raw, null, 2)}</pre>}
      </Section>
      <TechDetails data={q} />
    </Modal>
  )
}

/** One run: how it ended in plain words, then the numbers, then the raw record. */
export function RunDetail({ r, onClose }: { r: RunRecord; onClose: () => void }) {
  const drift = r.error?.code === 'schema_drift'
  const failed = r.status === 'failed'
  const info = r.error ? describe(r.error.code, r.error.message) : null
  const id = (r as RunRecord & { run_id?: string }).run_id
  return (
    <Modal title={id ? `Run details · ${id}` : 'Run details'} subtitle={`${r.integration} · ${r.action}, ${r.trigger === 'schedule' ? 'started by the schedule' : r.trigger === 'manual' ? 'started by hand' : 'a test run (ignored by health)'}.`} onClose={onClose} size="lg"
      footer={<><span className="mdl-foot-note">Test runs are shown here but never count towards an integration's health.</span><Button type="button" onClick={onClose}>Close</Button></>}>
      {failed && <Banner tone="failed" title={info?.title ?? 'The run failed'} next={info?.next}>{info?.explain} {r.error?.message && messageAddsInfo(r.error.code) && <span className="muted">({r.error.message})</span>}</Banner>}
      {!failed && drift && <Banner tone="warning" title={info?.title ?? 'The run succeeded with a warning'} next={info?.next}>{r.error?.message || info?.explain}</Banner>}
      {!failed && !drift && r.status === 'running' && <Banner tone="info" title="Still running">It has not finished yet. Reload in a moment.</Banner>}
      {!failed && !drift && r.status === 'success' && r.records_invalid > 0 && (
        <Banner tone="warning" title={`Finished, but ${r.records_invalid} record${r.records_invalid === 1 ? ' was' : 's were'} set aside`} next={<>Open <Link to="/quarantine" onClick={onClose}>Quarantine</Link> to see why and fix it.</>}>
          {r.records_valid} record{r.records_valid === 1 ? '' : 's'} were saved normally.
        </Banner>
      )}
      {!failed && !drift && r.status === 'success' && r.records_invalid === 0 && <Banner tone="success" title="The run succeeded">{r.records_valid} record{r.records_valid === 1 ? '' : 's'} saved, none set aside.</Banner>}
      <Section title="The numbers">
        <KeyValue rows={[['Started', when(r.started_at)], ['Took', r.duration_ms != null ? `${r.duration_ms} ms` : null], ['Pages fetched', r.pages_fetched], ['Records pulled', r.records_pulled],
          ['Saved', r.records_valid], ['Set aside (quarantined)', r.records_invalid], ['Retries', r.retries], ['Type', r.mode === 'pull' ? 'scheduled pull' : 'on-demand lookup']]} />
      </Section>
      <TechDetails data={r} />
    </Modal>
  )
}
