import type { TestResponse } from '../api/client'
import { describe, parseNote } from '../lib/errors'
import { Banner, KeyValue, RecordTable, Section, TechDetails } from './modal-parts'

type Context = { integration?: string; action?: string; host?: string | null }

// B-3: what a test call found, in plain words first: a verdict, the cause and next step if it failed, the facts, one mapped record
// as a table, and the raw reply tucked away under Technical details.
export function TestResult({ r, integration, action, host }: { r: TestResponse } & Context) {
  const failure = r.ok ? null : r.notes.map(parseNote).find(n => n.code) ?? (r.notes[0] ? { code: null, message: r.notes[0] } : null)
  const info = failure ? describe(failure.code, failure.message) : null
  const plainNotes = r.notes.map(parseNote).filter(n => !n.code).map(n => n.message).filter(m => m !== failure?.message)
  const gaps = r.missing_paths
  const mapped = r.mapped_sample as Record<string, unknown> | null

  return (
    <div className="mdl-stack">
      {!r.ok && (
        <Banner tone="failed" title={info?.title ?? 'The test did not succeed'} next={info?.next}>
          {info?.explain ?? failure?.message ?? 'The service could not be tested.'}
        </Banner>
      )}
      {r.ok && !mapped && (
        <Banner tone="warning" title="Connected, but the first page had no records" next="Check Records path in the action, and that this account can see any records.">
          We reached {host ?? 'the service'} and it answered, but nothing came back to map.
        </Banner>
      )}
      {r.ok && mapped && gaps.length > 0 && (
        <Banner tone="warning" title={`Connected, but ${gaps.length} mapped field${gaps.length === 1 ? '' : 's'} found nothing`} next="Open Edit and correct the paths listed below, then test again.">
          The service answered and the first record was mapped, but the paths below were not in the reply.
        </Banner>
      )}
      {r.ok && mapped && gaps.length === 0 && (
        <Banner tone="success" title="The connection works">
          We reached {host ?? 'the service'}, read the first page and mapped a record. Nothing was saved.
        </Banner>
      )}

      <Section title="What was tested">
        <KeyValue rows={[
          ['Integration', integration],
          ['Action', action],
          ['Host called', host ? <span className="mono">{host}</span> : null],
          ['HTTP status', r.status_code ?? 'no reply'],
          ['Time taken', r.latency_ms != null ? `${r.latency_ms} ms` : null],
          ['Pages fetched', r.pages_fetched],
        ]} />
      </Section>

      {mapped && (
        <Section title="First record, as it would be saved" hint="Each field of the common schema, filled from the service's reply.">
          <RecordTable record={mapped} />
        </Section>
      )}

      {gaps.length > 0 && (
        <Section title="Paths that found nothing" hint="These mapped fields were empty in the real reply.">
          <div>{gaps.map(p => <span className="missing" key={p}>{p}</span>)}</div>
        </Section>
      )}

      {plainNotes.length > 0 && (
        <Section title="Notes"><ul className="bullets">{plainNotes.map((n, i) => <li key={i}>{n}</li>)}</ul></Section>
      )}

      <TechDetails data={{ status_code: r.status_code, latency_ms: r.latency_ms, pages_fetched: r.pages_fetched, error_code: failure?.code ?? null, notes: r.notes,
        missing_paths: r.missing_paths, raw_sample: r.raw_sample, mapped_sample: r.mapped_sample }} />
    </div>
  )
}
