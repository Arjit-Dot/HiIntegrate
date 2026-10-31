// A small reference implementation of how a config's `map` turns a raw record into a result.
// It exists to check the fixtures. The real engine must behave the same way.
import fs from 'fs';
import jmespath from 'jmespath';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import { fileURLToPath } from 'url';

const resultSchema = JSON.parse(fs.readFileSync(fileURLToPath(new URL('../../result.schema.json', import.meta.url)), 'utf8'));
const ajv = new Ajv2020({ allErrors: true, allowUnionTypes: true });
addFormats(ajv);
ajv.addSchema(resultSchema);
export const validatorFor = (name) => ajv.getSchema(resultSchema.$id + '#/$defs/' + name);

export const FIELDS = {
  user: ['id', 'name', 'email', 'status', 'last_login'],
  device: ['id', 'hostname', 'ip', 'os', 'owner', 'last_seen'],
  alert: ['id', 'type', 'severity', 'timestamp', 'description'],
};
export const FETCHED_AT = '2026-01-01T09:05:00Z';
export const QUARANTINED_AT = '2026-01-01T09:05:03Z';

function toIso(v) {
  let d;
  if (typeof v === 'number' || /^\d+$/.test(String(v))) { let n = Number(v); if (n < 1e11) n *= 1000; d = new Date(n); } else d = new Date(v);
  if (isNaN(d)) throw new Error('bad date');
  return d.toISOString().replace('.000Z', 'Z');
}
function transform(v, t) {
  switch (t) {
    case 'string': return String(v);
    case 'int': { const n = parseInt(v, 10); if (isNaN(n)) throw new Error('bad int'); return n; }
    case 'float': { const n = parseFloat(v); if (isNaN(n)) throw new Error('bad float'); return n; }
    case 'bool': return ['true', '1', 'yes'].includes(String(v).toLowerCase());
    case 'lowercase': return String(v).toLowerCase();
    case 'uppercase': return String(v).toUpperCase();
    case 'datetime': return toIso(v);
    default: return v;
  }
}
const empty = (v) => v === undefined || v === null || v === '';

// Rules:
//  - a missing or null path uses `default` if given, otherwise the field stays empty (null)
//  - transform runs first (a failure is `transform_failed`), then value_map
//  - a value not in value_map uses `default` if given, otherwise the record is `invalid_value`
//  - every field in `required`, and always `id`, must be present (`missing_required_field`)
//  - the finished record must match the result schema (otherwise `invalid_value`)
export function mapRecord(cfg, actionName, rec, runId = 'run-0001') {
  const a = cfg.actions[actionName];
  const out = {};
  const fail = (reason, field) => ({ quarantine: { source: cfg.name, action: actionName, target_schema: a.target_schema, run_id: runId, raw: rec, reason, field, created_at: QUARANTINED_AT } });
  for (const field of FIELDS[a.target_schema]) {
    const entry = a.map[field];
    if (entry === undefined) continue;
    const e = typeof entry === 'string' ? { path: entry } : entry;
    let v = e.path ? jmespath.search(rec, e.path) : undefined;
    if (empty(v)) v = e.default !== undefined ? e.default : null;
    else {
      try { if (e.transform) v = transform(v, e.transform); } catch (err) { return fail('transform_failed', field); }
      if (e.value_map) {
        const k = String(v);
        if (k in e.value_map) v = e.value_map[k];
        else if (e.default !== undefined) v = e.default;
        else return fail('invalid_value', field);
      }
    }
    out[field] = v;
  }
  for (const f of new Set(['id', ...(a.required || [])])) if (empty(out[f])) return fail('missing_required_field', f);
  const record = {};
  for (const f of FIELDS[a.target_schema]) if (f in out) record[f] = out[f];
  record.source = cfg.name;
  record.fetched_at = FETCHED_AT;
  const check = validatorFor(a.target_schema);
  if (!check(record)) { const bad = check.errors[0]; return fail('invalid_value', (bad.instancePath || '/' + (bad.params.additionalProperty || '')).slice(1)); }
  return { record };
}
// Map every record of a list of pages, using the action's records_path.
export function runAction(cfg, actionName, pages) {
  const a = cfg.actions[actionName];
  const records = [], quarantine = [];
  for (const page of pages) {
    const list = a.records_path && a.records_path !== '@' ? jmespath.search(page, a.records_path) : page;
    for (const rec of list) { const r = mapRecord(cfg, actionName, rec); if (r.record) records.push(r.record); else quarantine.push(r.quarantine); }
  }
  return { records, quarantine };
}
