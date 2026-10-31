// Verifies the contract end to end. Run from schema/tools:  npm install && npm run check
// With --write it regenerates the expected files instead of comparing against them.
//
// It checks that:
//  1. both schemas compile,
//  2. every config in templates/ and docs/ is valid,
//  3. every config in samples/invalid/ fails with exactly the errors in expected-errors.json,
//  4. mapping the raw samples through the templates gives exactly docs/examples/expected/*.json,
//  5. every record, quarantine entry, run record and health example matches result.schema.json.
// The OpenAPI file is checked separately (see schema/README.md).
import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';
import { fileURLToPath } from 'url';
import { checkConfig } from './lib/config-check.mjs';
import { mapRecord, runAction, validatorFor } from './lib/map-engine.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const WRITE = process.argv.includes('--write');
const p = (...a) => path.join(ROOT, ...a);
const readJson = (rel) => JSON.parse(fs.readFileSync(p(rel), 'utf8'));
const readYaml = (rel) => yaml.load(fs.readFileSync(p(rel), 'utf8'));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
let failures = 0;
const check = (label, ok, extra) => { console.log((ok ? 'PASS ' : 'FAIL ') + label); if (!ok) { failures++; if (extra !== undefined) console.log('     ' + JSON.stringify(extra).slice(0, 600)); } };
const writeJson = (rel, obj) => { fs.mkdirSync(path.dirname(p(rel)), { recursive: true }); fs.writeFileSync(p(rel), JSON.stringify(obj, null, 2) + '\n'); };
// Compare to the committed file, or write it.
const expect = (rel, actual) => {
  if (WRITE) { writeJson(rel, actual); console.log('WROTE ' + rel); return; }
  check(rel + ' matches', fs.existsSync(p(rel)) && same(readJson(rel), actual), fs.existsSync(p(rel)) ? undefined : 'missing file');
};

// 1 + 2: configs
const good = [...fs.readdirSync(p('templates')).filter(f => f.endsWith('.yaml')).map(f => 'templates/' + f), 'docs/reference-config.yaml', 'docs/reference-config.clean.yaml'];
for (const f of good) { const errs = checkConfig(readYaml(f)).filter(i => i.severity === 'error'); check('valid config: ' + f, errs.length === 0, errs); }

// 3: invalid configs
const invDir = 'samples/invalid';
const invalid = fs.readdirSync(p(invDir)).filter(f => f.endsWith('.yaml')).sort();
const expectedErrors = {};
for (const f of invalid) {
  const issues = checkConfig(readYaml(invDir + '/' + f));
  expectedErrors[f] = issues;
  check('invalid config is rejected: ' + f, issues.some(i => i.severity === 'error'));
}
expect(invDir + '/expected-errors.json', expectedErrors);
expect('docs/examples/validate-response.json', { valid: false, errors: expectedErrors['several-problems.yaml'] });

// 4: mapping the samples
const cfg = (n) => readYaml('templates/' + n + '.yaml');
const gh = cfg('github'), jira = cfg('jira'), okta = cfg('okta');
const one = (c, action, file) => mapRecord(c, action, readJson(file));
const nextLink = (h) => { const m = /<([^>]+)>;\s*rel="next"/.exec(h.Link || ''); return m ? m[1] : null; };
let page = 1, pages = 1; for (;;) { const nx = nextLink(readJson(`samples/github/members_page${page}.headers.json`)); if (!nx) break; page = Number(/[?&]page=(\d+)/.exec(nx)[1]); pages++; }
check('GitHub next_link walk reaches the last page after 3 pages', pages === 3, pages);

const results = {
  'github-members': runAction(gh, 'list_members', [1, 2, 3].map(i => readJson(`samples/github/members_page${i}.json`))),
  'jira-users': runAction(jira, 'list_users', ['users_search_page1', 'users_search_page2', 'users_search_page3_empty'].map(n => readJson(`samples/jira/${n}.json`))),
  'okta-users': runAction(okta, 'list_users', [readJson('samples/okta/users.json')]),
  'okta-devices': runAction(okta, 'list_devices', [readJson('samples/okta/devices.json')]),
  'okta-alerts': runAction(okta, 'list_alerts', [readJson('samples/okta/logs.json')]),
};
const counts = { 'github-members': 8, 'jira-users': 4, 'okta-users': 4, 'okta-devices': 2, 'okta-alerts': 4 };
for (const [k, r] of Object.entries(results)) { check(`${k}: ${counts[k]} records, none quarantined`, r.records.length === counts[k] && r.quarantine.length === 0, r); expect(`docs/examples/expected/${k}.json`, r.records); }
const lookups = { 'github-get-user': one(gh, 'get_user', 'samples/github/get_user.json'), 'jira-get-user': one(jira, 'get_user', 'samples/jira/get_user.json'), 'okta-get-user': one(okta, 'get_user', 'samples/okta/get_user.json'), 'okta-get-device': one(okta, 'get_device', 'samples/okta/get_device.json') };
for (const [k, r] of Object.entries(lookups)) { check(k + ' maps', !!r.record, r); if (r.record) expect(`docs/examples/expected/${k}.json`, r.record); }
const u = results['okta-users'].records;
check('Okta status words become ours, and a null lastLogin stays empty', u[1].status === 'suspended' && u[2].status === 'inactive' && u[3].last_login === null && u[1].email === 'alan@acme.com', u);
check('Okta severities map DEBUG, INFO, WARN, ERROR to low, low, medium, high', same(results['okta-alerts'].records.map(a => a.severity), ['low', 'medium', 'high', 'low']));
const j = results['jira-users'].records;
check('Jira active true and false become active and inactive, and a hidden email stays empty', j[0].status === 'active' && j[1].status === 'inactive' && j[1].email === null, j);

const bad = [
  runAction(gh, 'list_members', [readJson('samples/github/members_bad_record.json')]),
  runAction(jira, 'list_users', [readJson('samples/jira/users_search_bad_record.json')]),
  runAction(okta, 'list_users', [readJson('samples/okta/users_bad_record.json')]),
  runAction(okta, 'list_alerts', [readJson('samples/okta/logs_bad_record.json')]),
];
const quarantine = bad.flatMap(r => r.quarantine);
check('each bad sample keeps its good records and quarantines one', bad.every(r => r.records.length >= 1 && r.quarantine.length === 1), bad.map(r => [r.records.length, r.quarantine.length]));
check('quarantine reasons: missing_required_field, missing_required_field, transform_failed, missing_required_field', same(quarantine.map(q => q.reason), ['missing_required_field', 'missing_required_field', 'transform_failed', 'missing_required_field']), quarantine.map(q => q.reason));
const strict = JSON.parse(JSON.stringify(okta)); delete strict.actions.list_users.map.status.default;
const iv = mapRecord(strict, 'list_users', { id: '00u1x', status: 'BANNED', profile: { login: 'x@acme.com', email: 'x@acme.com' } });
check('a value outside value_map with no default is quarantined as invalid_value', iv.quarantine && iv.quarantine.reason === 'invalid_value' && iv.quarantine.field === 'status', iv);
quarantine.push(iv.quarantine);
expect('docs/examples/expected/quarantine.json', quarantine);

// 5: every example matches result.schema.json
const records = [...Object.values(results).flatMap(r => r.records), ...Object.values(lookups).map(r => r.record)];
const byTarget = (r) => (r.hostname !== undefined || r.last_seen !== undefined) ? 'device' : (r.severity !== undefined || r.timestamp !== undefined) ? 'alert' : 'user';
check('every expected record matches its result schema', records.every(r => validatorFor(byTarget(r))(r)), records.filter(r => !validatorFor(byTarget(r))(r)));
check('every quarantine entry matches the quarantine schema', quarantine.every(q => validatorFor('quarantine_record')(q)));
for (const f of ['run-records.json']) { const runs = readJson('docs/examples/' + f); check(f + ': every run matches run_record', runs.every(r => validatorFor('run_record')(r)), runs.filter(r => !validatorFor('run_record')(r)).map(r => validatorFor('run_record').errors)); }
const health = readJson('docs/examples/health-examples.json');
check('health-examples.json: all five statuses, each matches health', same(Object.keys(health).sort(), ['degraded', 'disabled', 'failing', 'healthy', 'never_run']) && Object.entries(health).every(([k, h]) => h.status === k && validatorFor('health')(h)), Object.entries(health).filter(([k, h]) => !validatorFor('health')(h)));

console.log(failures ? `\n${failures} check(s) failed` : '\nAll contract checks passed');
process.exit(failures ? 1 : 0);
