// Where a validation problem belongs: which form field shows it, and which line of the config text it is on.
// The backend sends a dotted path such as `actions.list_users.request.path` (D-6: path, message, severity).

export interface Placed {
  /** The form field to mark red, or null when the form has no field for it. */
  key: string | null
  /** Short name of that field, for the message. */
  label: string
  /** Form section 1 to 6 where the message is listed, or 0 for "no field for this". */
  section: number
  /** Set when the problem is in an action other than the one on screen. */
  elsewhere?: string
}

const TOP: Record<string, [string, string, number]> = {
  name: ['name', 'Name', 1], display_name: ['display_name', 'Display name', 1], category: ['category', 'Category', 1],
  description: ['description', 'Description', 1], enabled: ['enabled', 'Enabled', 1],
  base_url: ['base_url', 'Base URL', 2],
}
const AUTH: Record<string, [string, string]> = {
  type: ['authType', 'Auth type'], secret: ['secret', 'Secret name'], username: ['authUser', 'Username'],
  in: ['authIn', 'Placement'], name: ['authName', 'Header or parameter name'], prefix: ['authPrefix', 'Prefix'],
}
const PAGING: Record<string, [string, string]> = {
  type: ['pgType', 'Pagination'], source: ['pgSource', 'Link source'], header: ['pgHeader', 'Header or body path'], path: ['pgHeader', 'Header or body path'],
  offset_param: ['pgOffset', 'Offset parameter'], limit_param: ['pgLimitParam', 'Limit parameter'], limit: ['pgLimit', 'Page size'],
  total_path: ['pgTotal', 'Total path'], param: ['pgPageParam', 'Page parameter'], start: ['pgStart', 'First page'],
  cursor_param: ['pgCursorParam', 'Cursor parameter'], next_cursor_path: ['pgNextCursor', 'Next cursor path'], max_pages: ['maxPages', 'Max pages'],
}

const segments = (path: string) => path.replace(/\[(\d+)\]/g, '.$1').split('.').filter(Boolean)

export function locate(path: string, actionName: string): Placed {
  const s = segments(path)
  const [a, b] = s
  if (a === 'actions') {
    if (s[1] !== actionName) return { key: null, label: '', section: 4, elsewhere: s[1] }
    return locateAction(s.slice(2))
  }
  if (TOP[a]) return { key: TOP[a][0], label: TOP[a][1], section: TOP[a][2] }
  if (a === 'vars') return { key: 'vars', label: 'Variables', section: 2 }
  if (a === 'requires') return b === 'secrets' ? { key: 'secret', label: 'Secret name', section: 3 } : { key: 'vars', label: 'Variables', section: 2 }
  if (a === 'auth') { const f = AUTH[b] ?? ['authType', 'Authentication']; return { key: f[0], label: f[1], section: 3 } }
  if (a === 'alerts') return b === 'after_failures'
    ? { key: 'afterFailures', label: 'Failed runs before the email', section: 6 }
    : { key: 'recipients', label: 'Alert recipients', section: 6 }
  return { key: null, label: '', section: 0 }   // defaults, rate_limit, ...: no field in the form
}

function locateAction(s: string[]): Placed {
  const [a, b] = s
  const f = (key: string, label: string, section = 4): Placed => ({ key, label, section })
  switch (a) {
    case 'mode': return f('mode', 'Mode')
    case 'target_schema': return f('schema', 'Target schema')
    case 'schedule': return f('schedN', 'Schedule')
    case 'records_path': return f('records', 'Records path')
    case 'request': return b === 'method' ? f('method', 'Method') : b === 'query' ? f('query', 'Query parameters') : f('path', 'Path')
    case 'pagination': { const p = PAGING[b] ?? PAGING.type; return f(p[0], p[1]) }
    case 'inputs': return f('inputs', 'Inputs')
    case 'map': return b ? f(`map:${b}`, `Mapping for ${b}`, 5) : { key: null, label: 'Mapping', section: 5 }
    case 'required': return { key: null, label: 'Required fields', section: 5 }
    case 'error_when': return f('errPath', 'Treat a 200 reply as an error', 6)
    case 'on_invalid': return f('onInvalid', 'When a record is invalid', 6)
    case 'store': return f('store', 'Store results', 6)
    default: return { key: null, label: '', section: 0 }
  }
}

/** The 1-based line of a path in the config text (YAML or JSON), or null. Walks the keys in order, so repeated names are found in the right place. */
export function lineOf(text: string, path: string, fmt: 'yaml' | 'json'): number | null {
  const lines = text.split('\n')
  let at = 0, found: number | null = null
  for (const seg of segments(path)) {
    if (/^\d+$/.test(seg)) continue   // array index: stay on the key that holds the list
    const re = fmt === 'yaml'
      ? new RegExp(`^\\s*(-\\s+)?["']?${seg.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}["']?\\s*:`)
      : new RegExp(`"${seg.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"\\s*:`)
    let i = at
    while (i < lines.length && !re.test(lines[i])) i++
    if (i >= lines.length) break
    found = i + 1; at = i + 1
  }
  return found
}

/** A message like "{{vars.org}} is not defined in vars or requires.vars": the variable that is missing. */
export const missingVar = (message: string): string | null => /\{\{\s*vars\.(\w+)\s*\}\} is not defined/.exec(message)?.[1] ?? null
