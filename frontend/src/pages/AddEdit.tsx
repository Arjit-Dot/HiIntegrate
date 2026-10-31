import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import Editor from '@monaco-editor/react'
import * as yaml from 'js-yaml'
import { api, ApiError, type Config, type SecretInfo, type TestResponse } from '../api/client'
import { applyPreset, buildConfig, configToState, defaultState, hostOf, SCHEMAS, TRANSFORMS, type FormState, type SchemaName } from '../lib/config'
import { ErrorBox, Pill, useToast } from '../components/common'
import { TestResult } from '../components/TestResult'

type Issue = { path: string; message: string; severity: 'error' | 'warning' }
type Pane = 'config' | 'validate' | 'test'

export default function AddEdit() {
  const { id } = useParams()
  const templateId = useSearchParams()[0].get('template')
  const [requires, setRequires] = useState<Config | undefined>()   // from the template, to tell the person what to fill in
  const nav = useNavigate()
  const toast = useToast()
  const [s, setS] = useState<FormState>(defaultState)
  const [base, setBase] = useState<Config | undefined>()      // the saved config when editing (D-15: update in place)
  const [editedAction, setEditedAction] = useState<string | undefined>()
  const [exists, setExists] = useState(!!id)
  const [loadError, setLoadError] = useState('')
  const [raw, setRaw] = useState<string | null>(null)           // text typed in the editor, overrides the form
  const [fmt, setFmt] = useState<'yaml' | 'json'>('yaml')
  const [pane, setPane] = useState<Pane>('config')
  const [issues, setIssues] = useState<Issue[]>([])
  const [validating, setValidating] = useState(false)
  const [secrets, setSecrets] = useState<SecretInfo[]>([])
  const [test, setTest] = useState<TestResponse | null>(null)
  const [testErr, setTestErr] = useState('')
  const [testInputs, setTestInputs] = useState('{\n  "id": "1"\n}')
  const [busy, setBusy] = useState(false)

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => { setRaw(null); setS(p => ({ ...p, [k]: v })) }
  const bind = (k: keyof FormState) => ({
    value: s[k] as string,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => set(k, e.target.value as never),
  })

  useEffect(() => { api.listSecrets().then(r => setSecrets(r.items)).catch(() => {}) }, [])
  useEffect(() => {
    if (!id) return
    api.getIntegration(id).then(r => {
      setBase(r.config as Config)
      const st = configToState(r.config as Config)
      setS(st); setEditedAction(st.actionName)
    }).catch(e => setLoadError(e.message))
  }, [id])

  // "Use this template" (D-15: a template is only a starting point, so saving creates a NEW integration).
  useEffect(() => {
    if (id || !templateId) return
    api.getTemplate(templateId).then(r => {
      const c = r.config as Config
      setBase(c); setRequires(c.requires)
      const st = configToState(c)
      setS(st); setEditedAction(st.actionName)
    }).catch(e => setLoadError(e.message))
  }, [id, templateId])

  // The config: from the editor text if the person typed in it, otherwise built from the form.
  const parsed = useMemo<{ config?: Config; error?: string }>(() => {
    if (raw === null) return { config: buildConfig(s, base, editedAction) }
    try {
      const c = yaml.load(raw)
      if (!c || typeof c !== 'object' || Array.isArray(c)) return { error: 'The config must be a YAML or JSON object.' }
      return { config: c as Config }
    } catch (e) { return { error: (e as Error).message } }
  }, [s, base, editedAction, raw])

  const text = raw ?? (fmt === 'yaml'
    ? yaml.dump(parsed.config, { lineWidth: -1, noRefs: true })
    : JSON.stringify(parsed.config, null, 2))

  // Validation panel (B-2): the server is the only validator (D-12).
  const runValidate = useCallback(async (): Promise<boolean> => {
    if (parsed.error || !parsed.config) { setIssues([{ path: '(config)', message: parsed.error ?? 'Invalid config', severity: 'error' }]); return false }
    setValidating(true)
    try {
      const r = await api.validate(parsed.config)
      setIssues(r.errors as Issue[])
      return r.valid
    } catch (e) {
      setIssues([{ path: '(request)', message: (e as Error).message, severity: 'error' }])
      return false
    } finally { setValidating(false) }
  }, [parsed])
  useEffect(() => { const t = setTimeout(runValidate, 500); return () => clearTimeout(t) }, [runValidate])
  const errors = issues.filter(i => i.severity === 'error')

  async function persist(): Promise<string | null> {
    if (!(await runValidate())) { setPane('validate'); return null }
    const cfg = parsed.config!
    const name = String(cfg.name)
    if (s.secretValue && raw === null) {
      const host = hostOf(s.base_url, s.vars)
      if (!host) { toast('Fill in a valid Base URL first: the secret is pinned to its host.'); return null }
      try { await api.setSecret(s.secret, s.secretValue, host) }
      catch (e) {
        if (e instanceof ApiError && e.status === 501) toast('Secret store not available yet. Set SECRET_' + s.secret.toUpperCase() + ' in .env.')
        else { toast((e as Error).message); return null }
      }
    }
    try {
      if (exists) await api.replace(id ?? name, cfg); else await api.create(cfg)
      setExists(true)
      return name
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setPane('validate')
      toast((e as Error).message)
      return null
    }
  }
  async function save() {
    setBusy(true)
    const name = await persist()
    setBusy(false)
    if (name) { toast(`Saved ${name}`); nav('/integrations') }
  }
  async function runTest() {
    setBusy(true); setTest(null); setTestErr('')
    const name = await persist()
    if (name) {
      try {
        const isLookup = (parsed.config?.actions?.[s.actionName]?.mode ?? s.mode) === 'lookup'
        setTest(await api.test(name, s.actionName, isLookup ? JSON.parse(testInputs) : undefined))
      } catch (e) { setTestErr(e instanceof SyntaxError ? 'Inputs must be valid JSON.' : (e as Error).message) }
    }
    setBusy(false)
  }

  const known = secrets.find(x => x.name === s.secret)
  const host = hostOf(s.base_url, s.vars)
  const secretLabel = ({ bearer: 'Token', api_key: 'API key', basic: 'Password or API token' } as Record<string, string>)[s.authType] ?? 'Token'
  const actionNames = Object.keys(base?.actions ?? {})
  const pull = s.mode === 'pull'

  if (loadError) return <ErrorBox message={loadError} />

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>{id ? `Edit ${id}` : 'Add integration'}</h1>
          <p>Fill in the form. The config on the right is built live, and nothing is saved until it validates.{id && ' Saving updates this integration in place (D-15).'}</p>
        </div>
      </div>

      {templateId && !id && (
        <div className="callout">
          <strong>Started from the {templateId} template.</strong> Saving creates a new integration; the template itself is not changed.
          {requires?.vars && <ul>{Object.entries<any>(requires.vars).map(([k, v]) => <li key={k}>Set <code>{k}</code> in Variables: {v.label}{v.example ? <> (for example <code>{String(v.example)}</code>)</> : null}</li>)}</ul>}
          {requires?.secrets?.length ? <div className="hint">Needs the secret <code>{requires.secrets.join(', ')}</code>: enter its value in the Authentication section.</div> : null}
        </div>
      )}
      <div className="callout">
        <strong>What the platform requires</strong> <span className="muted">(fields marked <span className="star">*</span>)</span>
        <ul>
          <li>An integration <b>name</b> (a short slug), a <b>base URL</b>, and an <b>authentication</b> method with a <b>secret name</b> and its value (entered once, never shown again).</li>
          <li>At least one <b>action</b>: a <b>mode</b> (pull or lookup), a <b>target schema</b>, a <b>method</b> and a <b>path</b>.</li>
          <li>A mapping for <b>id</b>. The platform adds <code>source</code> and <code>fetched_at</code> itself.</li>
        </ul>
      </div>

      <div className="layout">
        <form className="card" autoComplete="off" onSubmit={e => e.preventDefault()}>
          <div className="section">
            <h2><span className="step">1</span>Identity</h2>
            <div className="grid">
              <div><label className="req">Name</label><input type="text" {...bind('name')} disabled={!!id} /><div className="hint">Slug: lowercase letters, digits, - or _. It becomes the <code>source</code> on every record.{id && ' Cannot change after creation.'}</div></div>
              <div><label>Display name</label><input type="text" {...bind('display_name')} /></div>
              <div><label>Category</label>
                <select {...bind('category')}>{['identity', 'threat_intel', 'ticketing', 'alerting', 'other'].map(c => <option key={c}>{c}</option>)}</select></div>
              <div className="inline" style={{ paddingTop: 22 }}>
                <Switch checked={s.enabled} onCheckedChange={v => set('enabled', v)} aria-label="Enabled" />
                <span>Enabled (scheduled runs happen)</span></div>
              <div className="full"><label>Description</label><textarea {...bind('description')} /></div>
            </div>
          </div>

          <div className="section">
            <h2><span className="step">2</span>Connection</h2>
            <div className="grid">
              <div className="full"><label className="req">Base URL</label><input type="text" className="mono" {...bind('base_url')} /><div className="hint">May contain <code>{'{{vars.x}}'}</code>, so one template works for any tenant. No other placeholders here.</div></div>
              <div className="full"><label>Variables</label><textarea className="mono" placeholder="domain=acme" {...bind('vars')} /><div className="hint">One <code>name=value</code> per line. These are plain settings, not secrets.</div></div>
            </div>
          </div>

          <div className="section">
            <h2><span className="step">3</span>Authentication</h2>
            <div className="grid">
              <div><label className="req">Type</label>
                <select {...bind('authType')}>
                  <option value="bearer">bearer (Authorization: Bearer …)</option><option value="api_key">api_key (header or query)</option><option value="basic">basic (username and token)</option>
                </select></div>
              <div><label className="req">Secret name</label><input type="text" className="mono" {...bind('secret')} /><div className="hint">The <b>name</b> goes in the config. The value never does.</div></div>
              <div className="full"><label>{secretLabel}</label>
                <input type="password" autoComplete="new-password" placeholder="Paste the value here" {...bind('secretValue')} />
                <div className="hint">{known?.set ? <Pill kind="set">set</Pill> : <Pill kind="notset">not set</Pill>} Write-only: stored encrypted, never shown again, and never part of the config. Leave it blank to keep the current value.</div>
                <div className="hint">
                  {host
                    ? known?.host && known.host !== host && !s.secretValue
                      ? <>This secret is pinned to <code>{known.host}</code>. This integration sends requests to <code>{host}</code>, so it will be refused until you enter the value again.</>
                      : <>Pinned to <code>{host}</code> (from the Base URL). The platform refuses to send this secret anywhere else.</>
                    : 'The host comes from the Base URL, once it is filled in.'}
                </div></div>
              {s.authType === 'api_key' && <>
                <div><label>Placement</label><select {...bind('authIn')}><option>header</option><option>query</option></select></div>
                <div><label className="req">Header or parameter name</label><input type="text" {...bind('authName')} /></div>
                <div><label>Prefix</label><input type="text" placeholder='e.g. "SSWS " or "Token "' {...bind('authPrefix')} /></div>
              </>}
              {s.authType === 'basic' && <div><label className="req">Username</label><input type="text" placeholder="me@company.com" {...bind('authUser')} /><div className="hint">Not a secret, so it is kept in the config.</div></div>}
            </div>
            <div className="hint" style={{ marginTop: 10 }}>OAuth2 is reserved in the schema and not available yet.</div>
          </div>

          <div className="section">
            <h2><span className="step">4</span>Action</h2>
            {id && (
              <div className="actions-bar">
                <select style={{ width: 'auto' }} value={editedAction ?? ''} onChange={e => { setRaw(null); setS(configToState(base!, e.target.value)); setEditedAction(e.target.value) }}>
                  {editedAction === undefined && <option value="">(new action)</option>}
                  {actionNames.map(n => <option key={n}>{n}</option>)}
                </select>
                <Button variant="secondary" size="sm" type="button"  onClick={() => { setRaw(null); setEditedAction(undefined); setS(p => ({ ...applyPreset(p, 'user', 'pull'), actionName: 'new_action' })) }}>+ Add action</Button>
              </div>
            )}
            <div className="grid">
              <div><label className="req">Action name</label><input type="text" className="mono" {...bind('actionName')} /></div>
              <div><label className="req">Mode</label>
                <select value={s.mode} onChange={e => { setRaw(null); setS(p => applyPreset(p, p.schema, e.target.value)) }}>
                  <option value="pull">pull (scheduled, many records)</option><option value="lookup">lookup (on demand, one record)</option></select></div>
              <div><label className="req">Target schema</label>
                <select value={s.schema} onChange={e => { setRaw(null); setS(p => applyPreset(p, e.target.value as SchemaName)) }}>
                  <option>user</option><option>device</option><option>alert</option></select></div>
              <div><label className="req">Method</label><select {...bind('method')}><option>GET</option><option>POST</option></select></div>
              <div className="full"><label className="req">Path</label><input type="text" className="mono" {...bind('path')} /><div className="hint">Lookups may use <code>{'{{input.name}}'}</code>. Pulls may not.</div></div>
              <div className="full"><label>Query parameters</label><textarea className="mono" placeholder="limit=100" {...bind('query')} /><div className="hint">One <code>name=value</code> per line. <code>{'{{now - 24h}}'}</code> works for time windows.</div></div>
              <div className="full"><label>Records path</label><input type="text" className="mono" {...bind('records')} /><div className="hint">Where the list sits in the response. <code>@</code> means the response itself.</div></div>
            </div>

            {pull && (
              <div style={{ marginTop: 16 }} className="grid">
                <div><label className="req">Schedule</label>
                  <div className="inline"><span className="muted">every</span><input type="number" min={1} style={{ width: 90 }} {...bind('schedN')} />
                    <select style={{ width: 120 }} {...bind('schedU')}><option value="s">seconds</option><option value="m">minutes</option><option value="h">hours</option><option value="d">days</option></select></div>
                  <div className="hint">Minimum 10 seconds.</div></div>
                <div><label>Pagination</label><select {...bind('pgType')}>{['none', 'next_link', 'offset', 'page_number', 'cursor'].map(t => <option key={t}>{t}</option>)}</select></div>
                {s.pgType === 'next_link' && <>
                  <div><label>Link source</label><select {...bind('pgSource')}><option>header</option><option>body</option></select></div>
                  <div><label>Header or body path</label><input type="text" {...bind('pgHeader')} /></div></>}
                {s.pgType === 'offset' && <>
                  <div><label>Offset parameter</label><input type="text" {...bind('pgOffset')} /></div>
                  <div><label>Limit parameter</label><input type="text" {...bind('pgLimitParam')} /></div>
                  <div><label>Page size</label><input type="number" min={1} {...bind('pgLimit')} /></div>
                  <div><label>Total path (optional)</label><input type="text" placeholder="meta.total" {...bind('pgTotal')} /></div></>}
                {s.pgType === 'page_number' && <>
                  <div><label>Page parameter</label><input type="text" {...bind('pgPageParam')} /></div>
                  <div><label>First page</label><input type="number" min={0} {...bind('pgStart')} /></div></>}
                {s.pgType === 'cursor' && <>
                  <div><label>Cursor parameter</label><input type="text" {...bind('pgCursorParam')} /></div>
                  <div><label>Next cursor path</label><input type="text" {...bind('pgNextCursor')} /></div></>}
                <div><label>Max pages</label><input type="number" min={1} {...bind('maxPages')} /><div className="hint">Safety cap. Default 100.</div></div>
              </div>
            )}

            {!pull && (
              <div style={{ marginTop: 16 }}>
                <label className="req">Inputs</label>
                <div className="hint" style={{ margin: '-2px 0 8px' }}>The values the caller must supply. Types are checked before any request is sent.</div>
                {s.inputs.map((inp, n) => {
                  const upd = (patch: Partial<typeof inp>) => set('inputs', s.inputs.map((x, j) => (j === n ? { ...x, ...patch } : x)))
                  return (
                    <div className="inrow" key={n}>
                      <input type="text" className="mono" placeholder="name" value={inp.name} onChange={e => upd({ name: e.target.value })} />
                      <select value={inp.type} onChange={e => upd({ type: e.target.value })}>{['string', 'int', 'ip', 'domain', 'hash', 'enum'].map(t => <option key={t}>{t}</option>)}</select>
                      <input type="text" placeholder="enum values, comma separated" value={inp.values} onChange={e => upd({ values: e.target.value })} />
                      <label className="inline" style={{ margin: 0 }}><input type="checkbox" checked={inp.required} onChange={e => upd({ required: e.target.checked })} /> req.</label>
                      <Button variant="secondary" size="sm" type="button"  title="Remove" onClick={() => set('inputs', s.inputs.filter((_, j) => j !== n))}>×</Button>
                    </div>
                  )
                })}
                <Button variant="secondary" size="sm" type="button"  onClick={() => set('inputs', [...s.inputs, { name: '', type: 'string', values: '', required: true }])}>+ Add input</Button>
              </div>
            )}
          </div>

          <div className="section">
            <h2><span className="step">5</span>Field mapping <Pill kind="schema">{s.schema}</Pill></h2>
            <div className="hint" style={{ margin: '-6px 0 10px' }}>Left: our field. Right: where to find it in the response (JMESPath). <code>||</code> means "use the first that exists".</div>
            <div className="maphead"><span>Our field</span><span>Path in response</span><span>Transform</span><span>Required</span></div>
            {SCHEMAS[s.schema].fields.map(f => {
              const m = s.map[f] ?? { path: '', transform: '', required: false, valueMap: '' }
              const upd = (patch: Partial<typeof m>) => set('map', { ...s.map, [f]: { ...m, ...patch } })
              const en = SCHEMAS[s.schema].enums[f]
              return (
                <div className="maprow" key={f}>
                  <div className="field">{f}{f === 'id' && <span className="tag">always required</span>}</div>
                  <input type="text" className="mono" placeholder="path in response" value={m.path} onChange={e => upd({ path: e.target.value })} />
                  <select value={m.transform} onChange={e => upd({ transform: e.target.value })}>{TRANSFORMS.map(t => <option key={t} value={t}>{t || 'none'}</option>)}</select>
                  <label className="inline" style={{ margin: 0, justifyContent: 'center' }}><input type="checkbox" checked={f === 'id' || m.required} disabled={f === 'id'} onChange={e => upd({ required: e.target.checked })} /></label>
                  {en && <div className="vm"><input type="text" className="mono" placeholder="value map, e.g. ACTIVE=active, OFF=inactive" value={m.valueMap} onChange={e => upd({ valueMap: e.target.value })} /><div className="hint">Allowed values: {en.join(', ')}</div></div>}
                </div>
              )
            })}
          </div>

          <div className="section">
            <h2><span className="step">6</span>Errors and alerts</h2>
            <div className="grid">
              <div><label>When a record is invalid</label>
                <select {...bind('onInvalid')}><option value="quarantine">quarantine (save it with the reason)</option><option value="skip">skip (drop it, count it)</option></select></div>
              <div className="inline" style={{ paddingTop: 22 }}>
                <Switch checked={s.store} onCheckedChange={v => set('store', v)} aria-label="Store results" /><span>Store results</span></div>
              <div className="full"><label>Treat a 200 reply as an error when… <span className="muted">(optional)</span></label>
                <div className="grid three">
                  <input type="text" placeholder="path, e.g. ok" {...bind('errPath')} />
                  <input type="text" placeholder="equals, e.g. false" {...bind('errEq')} />
                  <input type="text" placeholder="message path, e.g. error" {...bind('errMsg')} />
                </div></div>
              <div><label>Email after this many failed runs in a row</label><input type="number" min={1} {...bind('afterFailures')} /></div>
              <div><label>Alert recipients</label><input type="text" placeholder="secops@example.com, oncall@example.com" {...bind('recipients')} /></div>
            </div>
          </div>
        </form>

        <aside className="card sticky">
          <Tabs value={pane} onValueChange={v => setPane(v as Pane)}>
            <TabsList className="h-auto w-full justify-start gap-1 rounded-none border-b border-border bg-transparent px-3 pt-2.5">
              <TabsTrigger value="config" className="flex-none rounded-none border-0 border-b-2 border-transparent px-3 py-2 font-semibold text-muted-foreground shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-secondary-foreground data-[state=active]:shadow-none">Config</TabsTrigger>
              <TabsTrigger value="validate" className="flex-none rounded-none border-0 border-b-2 border-transparent px-3 py-2 font-semibold text-muted-foreground shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-secondary-foreground data-[state=active]:shadow-none">Validation {errors.length > 0 && <Pill kind="failed">{errors.length}</Pill>}</TabsTrigger>
              <TabsTrigger value="test" className="flex-none rounded-none border-0 border-b-2 border-transparent px-3 py-2 font-semibold text-muted-foreground shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-secondary-foreground data-[state=active]:shadow-none">Test connection</TabsTrigger>
            </TabsList>
          </Tabs>

          {pane === 'config' && (
            <div className="pane active">
              <div className="actions-bar">
                <div className="seg">
                  {(['yaml', 'json'] as const).map(f => (
                    <button type="button" key={f} className={fmt === f ? 'active' : ''} onClick={() => {
                      if (raw !== null && parsed.config) setRaw(f === 'yaml' ? yaml.dump(parsed.config, { lineWidth: -1 }) : JSON.stringify(parsed.config, null, 2))
                      setFmt(f)
                    }}>{f.toUpperCase()}</button>
                  ))}
                </div>
                <Button variant="secondary" size="sm" type="button"  onClick={() => { navigator.clipboard.writeText(text); toast('Copied') }}>Copy</Button>
                {raw !== null && <Button variant="secondary" size="sm" type="button"  onClick={() => setRaw(null)} title="Throw away the typed text and rebuild from the form">Reset to form</Button>}
              </div>
              {raw !== null && <div className="hint" style={{ marginBottom: 8 }}>You are editing the config directly. Changing the form resets it.</div>}
              <Editor height="520px" language={fmt} value={text} onChange={v => v !== undefined && v !== text && setRaw(v)}
                options={{ minimap: { enabled: false }, fontSize: 12.5, scrollBeyondLastLine: false, wordWrap: 'on' }} />
            </div>
          )}

          {pane === 'validate' && (
            <div className="pane active">
              <div className="actions-bar">
                <Button type="button"  onClick={runValidate} disabled={validating}>{validating ? 'Validating…' : 'Validate'}</Button>
                <Button variant="secondary" type="button"  onClick={save} disabled={busy}>{busy ? 'Saving…' : id ? 'Save changes' : 'Save integration'}</Button>
              </div>
              {errors.length === 0 && <div className="issue ok"><div><b>Valid.</b> No errors{issues.length ? `, ${issues.length} warning${issues.length > 1 ? 's' : ''}` : ''}.</div></div>}
              {issues.map((i, n) => (
                <div className="issue" key={n} style={i.severity === 'warning' ? { background: 'var(--warn-bg)', color: '#78350f' } : undefined}>
                  <div><div className="p">{i.path}</div><div>{i.message}</div></div>
                </div>
              ))}
            </div>
          )}

          {pane === 'test' && (
            <div className="pane active">
              {!pull && <div style={{ marginBottom: 10 }}><label>Inputs (JSON)</label><textarea className="mono" value={testInputs} onChange={e => setTestInputs(e.target.value)} /></div>}
              <div className="actions-bar"><Button type="button"  onClick={runTest} disabled={busy}>{busy ? 'Working…' : 'Run test (first page only)'}</Button></div>
              <div className="hint" style={{ marginBottom: 10 }}>The test calls the saved integration, so this saves it first if it is valid.</div>
              {testErr && <ErrorBox message={testErr} />}
              {test ? <TestResult r={test} /> : !testErr && <div className="muted">Calls the service once, then shows the raw reply beside the mapped record and flags paths that were not found.</div>}
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}
