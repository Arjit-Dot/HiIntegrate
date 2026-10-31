// Form state <-> integration config. Ported from docs/ui-prototype.html (buildConfig, presets).
import type { Config } from '../api/client'

export type SchemaName = 'user' | 'device' | 'alert'
export const SCHEMAS: Record<SchemaName, { fields: string[]; enums: Record<string, string[]> }> = {
  user: { fields: ['id', 'name', 'email', 'status', 'last_login'], enums: { status: ['active', 'inactive', 'suspended', 'unknown'] } },
  device: { fields: ['id', 'hostname', 'ip', 'os', 'owner', 'last_seen'], enums: {} },
  alert: { fields: ['id', 'type', 'severity', 'timestamp', 'description'], enums: { severity: ['low', 'medium', 'high', 'critical', 'unknown'] } },
}
export const TRANSFORMS = ['', 'string', 'int', 'float', 'bool', 'lowercase', 'uppercase', 'datetime']

export interface MapRow { path: string; transform: string; required: boolean; valueMap: string; defaultValue?: string }
export interface InputRow { name: string; type: string; values: string; required: boolean }

export interface FormState {
  name: string; display_name: string; category: string; description: string; enabled: boolean
  vars: string; base_url: string
  authType: string; authIn: string; authName: string; authPrefix: string; authUser: string; authExtra: Config; secret: string; secretValue: string
  actionName: string; mode: string; schema: SchemaName; method: string; path: string; query: string; records: string
  schedN: string; schedU: string
  pgType: string; pgSource: string; pgHeader: string; pgOffset: string; pgLimitParam: string; pgLimit: string; pgTotal: string
  pgPageParam: string; pgStart: string; pgCursorParam: string; pgNextCursor: string; maxPages: string
  inputs: InputRow[]; map: Record<string, MapRow>
  onInvalid: string; store: boolean; errPath: string; errEq: string; errMsg: string
  afterFailures: string; recipients: string
}

const PRESETS: Record<SchemaName, { path: string; records: string; name: string; category: string; title: string; desc: string; map: Record<string, [string, string]>; vm: Record<string, string>; query: string }> = {
  user: { path: '/api/users', records: 'items', name: 'list_users', category: 'identity', title: 'Generic user source', desc: 'Starter for any service that lists users.',
    map: { id: ['id', 'string'], name: ['name', ''], email: ['email', 'lowercase'], status: ['status', ''], last_login: ['last_login', 'datetime'] },
    vm: { status: 'active=active, disabled=inactive, suspended=suspended' }, query: '' },
  device: { path: '/api/devices', records: 'items', name: 'list_devices', category: 'other', title: 'Generic device source', desc: 'Starter for any service that lists devices.',
    map: { id: ['id', 'string'], hostname: ['hostname', ''], ip: ['ip_address', ''], os: ['os', ''], owner: ['owner', ''], last_seen: ['last_seen', 'datetime'] }, vm: {}, query: '' },
  alert: { path: '/api/alerts', records: 'items', name: 'list_alerts', category: 'alerting', title: 'Generic alert source', desc: 'Starter for any service that lists alerts or events.',
    map: { id: ['id', 'string'], type: ['type', ''], severity: ['severity', ''], timestamp: ['created_at', 'datetime'], description: ['message', ''] },
    vm: { severity: 'info=low, warning=medium, error=high, critical=critical' }, query: 'since={{now - 24h}}' },
}

export function mapRowsFor(schema: SchemaName): Record<string, MapRow> {
  const pr = PRESETS[schema]
  const out: Record<string, MapRow> = {}
  SCHEMAS[schema].fields.forEach(f => {
    const [path, transform] = pr.map[f] ?? ['', '']
    out[f] = { path, transform, required: f === 'id', valueMap: pr.vm[f] ?? '' }
  })
  return out
}

export function defaultState(): FormState {
  const pr = PRESETS.user
  return {
    name: '', display_name: '', category: pr.category, description: '', enabled: true,
    vars: '', base_url: 'https://{{vars.domain}}.example.com',
    authType: 'bearer', authIn: 'header', authName: 'Authorization', authPrefix: '', authUser: '', authExtra: {}, secret: '', secretValue: '',
    actionName: pr.name, mode: 'pull', schema: 'user', method: 'GET', path: pr.path, query: pr.query, records: pr.records,
    schedN: '15', schedU: 'm',
    pgType: 'offset', pgSource: 'header', pgHeader: 'Link', pgOffset: 'offset', pgLimitParam: 'limit', pgLimit: '100', pgTotal: '',
    pgPageParam: 'page', pgStart: '1', pgCursorParam: 'after', pgNextCursor: 'meta.next', maxPages: '100',
    inputs: [], map: mapRowsFor('user'),
    onInvalid: 'quarantine', store: true, errPath: '', errEq: '', errMsg: '', afterFailures: '3', recipients: '',
  }
}

/** Switch schema or mode and refill the action fields from the preset. */
export function applyPreset(s: FormState, schema: SchemaName, mode = s.mode): FormState {
  const pr = PRESETS[schema]
  const lookup = mode === 'lookup'
  return {
    ...s, schema, mode,
    actionName: lookup ? 'get_' + schema : pr.name,
    path: lookup ? pr.path + '/{{input.id}}' : pr.path,
    records: lookup ? '@' : pr.records,
    query: lookup ? '' : pr.query,
    map: mapRowsFor(schema),
    inputs: lookup ? [{ name: 'id', type: 'string', values: '', required: true }] : [],
  }
}

function parseKV(text: string) {
  const o: Record<string, string | number> = {}
  String(text || '').split('\n').forEach(line => {
    const i = line.indexOf('=')
    if (i > 0) { const k = line.slice(0, i).trim(), v = line.slice(i + 1).trim(); if (k) o[k] = /^\d+$/.test(v) ? Number(v) : v }
  })
  return o
}
function parseVM(text: string) {
  const o: Record<string, string> = {}
  String(text || '').split(',').forEach(p => {
    const i = p.indexOf('=')
    if (i > 0) { const k = p.slice(0, i).trim(), v = p.slice(i + 1).trim(); if (k && v) o[k] = v }
  })
  return o
}
const kvText = (o: Record<string, unknown> = {}) => Object.entries(o).map(([k, v]) => `${k}=${v}`).join('\n')
const vmText = (o: Record<string, string> = {}) => Object.entries(o).map(([k, v]) => `${k}=${v}`).join(', ')
function parseEq(v: string): string | number | boolean {
  v = String(v || '').trim()
  if (v === 'true') return true
  if (v === 'false') return false
  if (/^-?\d+(\.\d+)?$/.test(v)) return Number(v)
  return v
}

const ACTION_KEYS = ['mode', 'target_schema', 'schedule', 'request', 'pagination', 'inputs', 'records_path', 'error_when', 'map', 'required', 'on_invalid', 'store']
const REQUEST_KEYS = ['method', 'path', 'query']
const TOP_KEYS = ['version', 'name', 'display_name', 'category', 'description', 'enabled', 'vars', 'requires', 'base_url', 'auth', 'actions', 'alerts']

/** Keys the form has no field for (headers, body, incremental, ...), taken from the saved config so nothing is lost. */
const extrasOf = (src: Config | undefined, known: string[]): Config =>
  Object.fromEntries(Object.entries(src ?? {}).filter(([k]) => !known.includes(k)))

/** The action built from the form. `saved` is the same action as last saved, if any; what the form cannot edit is kept. */
export function buildAction(s: FormState, saved?: Config): Config {
  const act: Config = { mode: s.mode, target_schema: s.schema }
  if (s.mode === 'pull') act.schedule = `every ${s.schedN}${s.schedU}`
  const rq: Config = { method: s.method, path: s.path }
  const q = parseKV(s.query)
  if (Object.keys(q).length) rq.query = q
  act.request = { ...rq, ...extrasOf(saved?.request, REQUEST_KEYS) }
  if (s.mode === 'pull' && s.pgType !== 'none') {
    const p: Config = { type: s.pgType }
    if (s.pgType === 'next_link') { p.source = s.pgSource; if (s.pgSource === 'header') p.header = s.pgHeader; else p.path = s.pgHeader }
    if (s.pgType === 'offset') { p.offset_param = s.pgOffset; p.limit_param = s.pgLimitParam; p.limit = Number(s.pgLimit) || 100; if (s.pgTotal) p.total_path = s.pgTotal }
    if (s.pgType === 'page_number') { p.param = s.pgPageParam; p.start = Number(s.pgStart); p.stop_when_empty = true }
    if (s.pgType === 'cursor') { p.cursor_param = s.pgCursorParam; p.next_cursor_path = s.pgNextCursor }
    p.max_pages = Number(s.maxPages) || 100
    act.pagination = p
  }
  if (s.mode === 'lookup') {
    const inputs: Config = {}
    s.inputs.forEach(i => {
      if (!i.name) return
      const o: Config = { type: i.type }
      if (i.type === 'enum') o.values = i.values.split(',').map(x => x.trim()).filter(Boolean)
      o.required = !!i.required
      inputs[i.name] = o
    })
    act.inputs = inputs
  }
  act.records_path = s.records || '@'
  if (s.errPath) act.error_when = { path: s.errPath, equals: parseEq(s.errEq), message_path: s.errMsg }
  const map: Config = {}, required: string[] = []
  SCHEMAS[s.schema].fields.forEach(f => {
    const m = s.map[f]
    const dflt = m?.defaultValue?.trim()
    if (!m || (!m.path && !dflt)) return
    const vm = parseVM(m.valueMap)
    if (!dflt && !m.transform && !Object.keys(vm).length) map[f] = m.path
    else {
      // A constant is allowed: no path, only a default (GitHub's `status: { default: active }`).
      const e: Config = {}
      if (m.path) e.path = m.path
      if (m.transform) e.transform = m.transform
      if (Object.keys(vm).length) e.value_map = vm
      if (dflt) e.default = dflt
      else if (Object.keys(vm).length) e.default = 'unknown'
      map[f] = e
    }
    if (m.required || f === 'id') required.push(f)
  })
  act.map = map
  act.required = required
  act.on_invalid = s.onInvalid
  if (!s.store) act.store = false
  return { ...extrasOf(saved, ACTION_KEYS), ...act }
}

/**
 * The whole config. When editing, `base` is the saved config: every other action is kept
 * untouched and only the action being edited is replaced (D-15: change in place).
 */
export function buildConfig(s: FormState, base?: Config, editedAction?: string): Config {
  const c: Config = { version: 1, name: s.name }
  if (s.display_name) c.display_name = s.display_name
  c.category = s.category
  if (s.description) c.description = s.description
  c.enabled = !!s.enabled
  const vars = parseKV(s.vars)
  if (Object.keys(vars).length) c.vars = vars
  const req: Config = {}
  // Keep the template's own labels and examples; make up a label only for a variable that has none.
  const savedVars = base?.requires?.vars ?? {}
  if (Object.keys(vars).length) { req.vars = {}; Object.keys(vars).forEach(k => (req.vars[k] = savedVars[k] ?? { label: k, example: String(vars[k]) })) }
  if (s.secret) req.secrets = [s.secret]
  if (Object.keys(req).length) c.requires = req
  c.base_url = s.base_url
  const a: Config = { type: s.authType }
  if (s.authType === 'api_key') { a.in = s.authIn; a.name = s.authName; if (s.authPrefix) a.prefix = s.authPrefix }
  if (s.authType === 'basic') a.username = s.authUser
  if (s.authType === 'oauth2_client_credentials') Object.assign(a, s.authExtra) // client_id, token_url, scope, audience (D-21): the form has no fields for them yet, so keep them
  a.secret = s.secret
  c.auth = a
  const to = s.recipients.split(',').map(x => x.trim()).filter(Boolean)
  if (to.length) c.alerts = { after_failures: Number(s.afterFailures) || 3, to }
  const actions: Config = {}
  const others = base?.actions ?? {}
  Object.keys(others).forEach(k => { if (k !== editedAction) actions[k] = others[k] })
  actions[s.actionName || 'action'] = buildAction(s, editedAction ? others[editedAction] : undefined)
  c.actions = actions
  // Top-level settings the form has no field for (defaults such as headers, rate_limit, ...) stay as saved.
  const { actions: built, ...head } = c
  return { ...head, ...extrasOf(base, TOP_KEYS), actions: built }
}

/** Fill the form from a saved config, showing one action. */
export function configToState(c: Config, actionName?: string): FormState {
  const s = defaultState()
  const names = Object.keys(c.actions ?? {})
  const an = actionName && c.actions?.[actionName] ? actionName : names[0]
  const act: Config = (an && c.actions[an]) || {}
  const auth = c.auth ?? {}
  const schema = (act.target_schema ?? 'user') as SchemaName
  const m = /^every\s+(\d+)\s*([smhd])/.exec(String(act.schedule ?? ''))
  const pg = act.pagination ?? {}
  const rows = mapRowsFor(schema)
  SCHEMAS[schema].fields.forEach(f => {
    const e = act.map?.[f]
    rows[f] = typeof e === 'string'
      ? { path: e, transform: '', required: (act.required ?? []).includes(f) || f === 'id', valueMap: '' }
      : e ? { path: e.path ?? '', transform: e.transform ?? '', required: (act.required ?? []).includes(f) || f === 'id', valueMap: vmText(e.value_map), defaultValue: e.default === undefined ? '' : String(e.default) }
        : { path: '', transform: '', required: false, valueMap: '' }
  })
  return {
    ...s,
    name: c.name ?? '', display_name: c.display_name ?? '', category: c.category ?? 'other', description: c.description ?? '', enabled: c.enabled ?? true,
    vars: kvText(c.vars), base_url: c.base_url ?? '',
    authType: auth.type ?? 'bearer', authIn: auth.in ?? 'header', authName: auth.name ?? 'Authorization', authPrefix: auth.prefix ?? '', authUser: auth.username ?? '', authExtra: Object.fromEntries(['client_id', 'token_url', 'scope', 'audience'].filter(k => auth[k] !== undefined).map(k => [k, auth[k]])), secret: auth.secret ?? '',
    actionName: an ?? 'action', mode: act.mode ?? 'pull', schema, method: act.request?.method ?? 'GET', path: act.request?.path ?? '', query: kvText(act.request?.query), records: act.records_path ?? '@',
    schedN: m ? m[1] : '15', schedU: m ? m[2] : 'm',
    pgType: pg.type ?? 'none', pgSource: pg.source ?? 'header', pgHeader: pg.header ?? pg.path ?? 'Link',
    pgOffset: pg.offset_param ?? 'offset', pgLimitParam: pg.limit_param ?? 'limit', pgLimit: String(pg.limit ?? 100), pgTotal: pg.total_path ?? '',
    pgPageParam: pg.param ?? 'page', pgStart: String(pg.start ?? 1), pgCursorParam: pg.cursor_param ?? 'after', pgNextCursor: pg.next_cursor_path ?? 'meta.next', maxPages: String(pg.max_pages ?? 100),
    inputs: Object.entries<any>(act.inputs ?? {}).map(([name, d]) => ({ name, type: d.type ?? 'string', values: (d.values ?? []).join(', '), required: d.required !== false })),
    map: rows, onInvalid: act.on_invalid ?? 'quarantine', store: act.store !== false,
    errPath: act.error_when?.path ?? '', errEq: act.error_when ? String(act.error_when.equals) : '', errMsg: act.error_when?.message_path ?? '',
    afterFailures: String(c.alerts?.after_failures ?? 3), recipients: (c.alerts?.to ?? []).join(', '),
  }
}

export function hostOf(url: string, varsText: string): string {
  let u = url
  const vars = parseKV(varsText)
  u = u.replace(/\{\{\s*vars\.(\w+)\s*\}\}/g, (_, k) => String(vars[k] ?? ''))
  try { return new URL(u).hostname.toLowerCase() } catch { return '' }
}
