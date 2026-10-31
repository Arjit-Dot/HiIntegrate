// Checks a config against schema/integration.schema.json, then applies the rules
// JSON Schema cannot express (see schema/README.md). This is a REFERENCE check used to
// verify the fixtures. The backend's config_loader must give the same answers.
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import fs from 'fs';
import { fileURLToPath } from 'url';

const schemaPath = fileURLToPath(new URL('../../integration.schema.json', import.meta.url));
const schema = JSON.parse(fs.readFileSync(schemaPath, 'utf8'));
const ajv = new Ajv2020({ allErrors: true, allowUnionTypes: true });
addFormats(ajv);
const validate = ajv.compile(schema);

const PH = /\{\{\s*([^}]*?)\s*\}\}/g;
function strings(o, path, out) {
  if (typeof o === 'string') out.push([path, o]);
  else if (Array.isArray(o)) o.forEach((v, i) => strings(v, path + '[' + i + ']', out));
  else if (o && typeof o === 'object') Object.entries(o).forEach(([k, v]) => strings(v, path ? path + '.' + k : k, out));
  return out;
}
function ajvPath(e) {
  const p = e.instancePath.replace(/^\//, '').replace(/\//g, '.');
  if (e.keyword === 'additionalProperties') return (p ? p + '.' : '') + e.params.additionalProperty;
  if (e.keyword === 'required') return (p ? p + '.' : '') + e.params.missingProperty;
  return p || '(root)';
}
export function checkConfig(cfg) {
  const issues = [];
  if (!validate(cfg)) {
    const msgFor = (e) => {
      const last = (ajvPath(e).split('.').pop() || '');
      switch (e.keyword) {
        case 'additionalProperties': return 'is not a known key';
        case 'required': return 'is required';
        case 'false schema': return 'is not allowed here (wrong mode or auth type)';
        case 'anyOf': return 'needs a path (or a default)';
        case 'propertyNames': return 'is not a field of the target schema';
        case 'const': return 'must be ' + JSON.stringify(e.params.allowedValue);
        case 'enum': return 'must be one of: ' + e.params.allowedValues.join(', ');
        case 'pattern':
          if (last === 'schedule') return 'must look like "every 10s", "every 5m", "every 2h" or "every 1d" (minimum 10 seconds)';
          if (last === 'secret') return 'must be a name (letters, digits, underscores, up to 64), not a key';
          if (last === 'base_url') return 'may only contain {{vars.x}} placeholders, and must start with http:// or https://';
          if (last === 'name') return 'must be a slug: lowercase letters, digits, - or _';
          if (last === 'path') return 'must start with /';
          return e.message;
        default: return e.message;
      }
    };
    for (const e of validate.errors) {
      if (['if', 'dependentSchemas'].includes(e.keyword)) continue;
      if (e.schemaPath.includes('/anyOf/')) continue;
      if (e.schemaPath.includes('/propertyNames/') && e.keyword !== 'propertyNames') continue;
      const path = e.keyword === 'propertyNames' ? (e.instancePath.replace(/^\//, '').replace(/\//g, '.') + '.' + e.params.propertyName) : ajvPath(e);
      issues.push({ path, message: msgFor(e), severity: 'error' });
    }
    if (!issues.length) issues.push({ path: '(root)', message: 'does not match the config schema', severity: 'error' });
    return dedupe(issues);
  }
  const known = new Set([...Object.keys(cfg.vars || {}), ...Object.keys((cfg.requires || {}).vars || {})]);
  const check = (path, text, ctx) => {
    let m; PH.lastIndex = 0;
    while ((m = PH.exec(text)) !== null) {
      const t = m[1];
      if (/^vars\.[A-Za-z_]\w*$/.test(t)) { if (!known.has(t.slice(5))) issues.push({ path, message: `{{${t}}} is not defined in vars or requires.vars`, severity: 'error' }); }
      else if (/^state\.[A-Za-z_]\w*$/.test(t)) { if (ctx.where === 'base_url') issues.push({ path, message: 'only {{vars.x}} is allowed in base_url', severity: 'error' }); }
      else if (/^now(\s*-\s*\d+[smhd])?$/.test(t)) { if (ctx.where === 'base_url') issues.push({ path, message: 'only {{vars.x}} is allowed in base_url', severity: 'error' }); }
      else if (/^input\.[A-Za-z_]\w*$/.test(t)) {
        if (ctx.mode !== 'lookup') issues.push({ path, message: `{{${t}}} is allowed only in lookup actions`, severity: 'error' });
        else if (!Object.keys(ctx.inputs || {}).includes(t.slice(6))) issues.push({ path, message: `{{${t}}} is used but not declared in inputs`, severity: 'error' });
      } else issues.push({ path, message: `unknown placeholder {{${t}}}. Use vars, input, state or now`, severity: 'error' });
    }
  };
  check('base_url', cfg.base_url, { where: 'base_url' });
  if (cfg.auth && cfg.auth.username) check('auth.username', cfg.auth.username, {});
  strings(cfg.defaults || {}, 'defaults', []).forEach(([p, s]) => check(p, s, {}));
  strings(cfg.vars || {}, 'vars', []).forEach(([p, s]) => check(p, s, {}));
  for (const [name, a] of Object.entries(cfg.actions)) {
    const base = 'actions.' + name;
    const ctx = { mode: a.mode, inputs: a.inputs };
    strings(a.request || {}, base + '.request', []).forEach(([p, s]) => check(p, s, ctx));
    strings(a.incremental || {}, base + '.incremental', []).forEach(([p, s]) => check(p, s, ctx));
    (a.required || []).forEach(f => { if (!(a.map && f in a.map)) issues.push({ path: base + '.required', message: `${f} is listed in required but is not in map`, severity: 'error' }); });
    if (a.mode === 'webhook') issues.push({ path: base + '.mode', message: 'webhook is reserved and not implemented yet', severity: 'error' });
    if (a.response_format && a.response_format !== 'json') issues.push({ path: base + '.response_format', message: a.response_format + ' is reserved and not implemented yet. Only json works', severity: 'error' });
    if ('fan_out' in a) issues.push({ path: base + '.fan_out', message: 'fan_out is reserved and not implemented yet', severity: 'error' });
    if (a.mode === 'pull' && a.map && !a.map.id) issues.push({ path: base + '.map.id', message: 'id must be mapped', severity: 'error' });
    if (a.mode === 'lookup' && a.map && !a.map.id) issues.push({ path: base + '.map.id', message: 'id must be mapped', severity: 'error' });
  }
  if (cfg.auth && cfg.auth.type === 'oauth2_client_credentials') issues.push({ path: 'auth.type', message: 'oauth2_client_credentials is reserved and not supported yet', severity: 'error' });
  if (cfg.requires && cfg.requires.secrets && cfg.auth && cfg.auth.secret && !cfg.requires.secrets.includes(cfg.auth.secret)) issues.push({ path: 'requires.secrets', message: `auth.secret ${cfg.auth.secret} is not listed in requires.secrets`, severity: 'warning' });
  return issues;
}
function dedupe(a) { const seen = new Set(); return a.filter(i => { const k = i.path + '|' + i.message; if (seen.has(k)) return false; seen.add(k); return true; }); }
