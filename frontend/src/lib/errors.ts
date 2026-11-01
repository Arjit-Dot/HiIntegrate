// One place that turns the backend's error codes into words a person can act on.
// Run and test errors come from result.schema.json; API errors from openapi.yaml; `unreachable` is raised by the client itself.
// Each entry: a short title, what happened, and what to do next. The raw code and message always stay available in "Technical details".

export type ErrorInfo = { title: string; explain: string; next: string }

export const ERROR_INFO: Record<string, ErrorInfo> = {
  secret_host_mismatch: {
    title: 'Request blocked to protect your key',
    explain: 'The saved key is only allowed to be sent to one host, and this config calls a different one. Nothing was sent.',
    next: 'Change the Base URL so it uses the host the key is pinned to, or save the key again for the new host on the Secrets page.',
  },
  auth_failed: {
    title: 'The service refused the login',
    explain: 'The service answered 401 or 403, so the key or token was rejected. The request was not retried.',
    next: 'Check that the key is correct, has not expired, and has the permissions this action needs. Set it again on the Secrets page if in doubt.',
  },
  connection_error: {
    title: 'Could not reach the service',
    explain: 'The connection failed or dropped, even after retrying.',
    next: 'Check the Base URL and your network, and that the service is running. Then try again.',
  },
  timeout: {
    title: 'The service took too long to answer',
    explain: 'No answer arrived before the time limit, even after retrying.',
    next: 'Try again in a moment. If it keeps happening, raise timeout_seconds in the config or ask whoever runs the service.',
  },
  server_error: {
    title: 'The service had an error',
    explain: 'The service answered with a 5xx error, even after retrying. This is a problem on their side.',
    next: 'Wait a little and try again.',
  },
  rate_limited: {
    title: 'The service asked us to slow down',
    explain: 'Too many requests were sent. The service answered 429, or you hit this app\'s own request limit.',
    next: 'Wait a minute and try again, or schedule this action less often.',
  },
  bad_response: {
    title: 'The reply was not what we expected',
    explain: 'The service answered, but the reply could not be read (not JSON, too large, or the records were not where the config says).',
    next: 'Check Records path in the action, and test again to see the real reply.',
  },
  api_error: {
    title: 'The service reported an error',
    explain: 'The reply came back fine but says something went wrong, which the config\'s error rule caught.',
    next: 'Read the message below. It usually says what to change.',
  },
  client_error: {
    title: 'The service rejected the request',
    explain: 'The service answered 4xx (for example 400 or 404), so something in the request is wrong: a path, a variable or an input.',
    next: 'Check the Path, the Variables and the inputs, then test again.',
  },
  schema_drift: {
    title: 'The service changed its reply shape',
    explain: 'A field the config maps was there in earlier runs and is now missing from every record. The run still succeeded.',
    next: 'Open Edit and update the mapping for the field that vanished.',
  },
  // API-level errors
  unauthorized: { title: 'You are signed out', explain: 'The sign-in ended or is missing.', next: 'Sign in again.' },
  validation_error: { title: 'Something needs fixing', explain: 'The request or the config did not pass the checks.', next: 'Fix the fields marked below and try again.' },
  not_found: { title: 'Not found', explain: 'That item does not exist, or it belongs to another account.', next: 'Go back and pick it from the list.' },
  conflict: { title: 'Already in use', explain: 'That name is taken, or this action is already running.', next: 'Pick another name, or try again in a moment.' },
  unsupported: { title: 'Not switched on', explain: 'The server does not have this feature enabled (for example the AI has no API key).', next: 'Everything else still works. Ask whoever runs the server to enable it.' },
  run_failed: { title: 'The run failed', explain: 'The action ran but ended in an error.', next: 'See the details below, and Run history for the full record.' },
  internal_error: { title: 'The app had an error', explain: 'Something went wrong inside the app, not in your config.', next: 'Try again. If it repeats, send the technical details to whoever runs the server.' },
  unreachable: { title: 'Cannot reach the app\'s server', explain: 'The dashboard could not contact its API.', next: 'Check that the stack is running (docker compose ps), then reload.' },
}

const GENERIC: ErrorInfo = {
  title: 'Request failed',
  explain: 'The request did not complete.',
  next: 'Try again. If it keeps failing, open Technical details and share them.',
}

export function errorInfo(code?: string | null): ErrorInfo {
  return (code && ERROR_INFO[code]) || GENERIC
}

/** The test route reports a failure as a note like `auth_failed: authentication failed (401). Not retried.` Split it. */
export function parseNote(note: string): { code: string | null; message: string } {
  const m = /^([a-z_]+): ([\s\S]*)$/.exec(note.trim())
  return m && ERROR_INFO[m[1]] ? { code: m[1], message: m[2] } : { code: null, message: note }
}

/** For secret_host_mismatch the message names the secret and both hosts. Pull them out so the explanation can use them. */
export function parseHostMismatch(message: string): { secret: string; pinned: string; called: string } | null {
  const m = /secret (\S+) is pinned to (\S+), but this request goes to ([^\s.]+(?:\.[^\s.]+)*)/.exec(message)
  return m ? { secret: m[1], pinned: m[2].replace(/,$/, ''), called: m[3] } : null
}

/** The friendly version of an error: title, explanation and next step, with the specifics filled in where the message has them. */
export function describe(code: string | null | undefined, message = ''): ErrorInfo & { code: string | null } {
  const base = errorInfo(code)
  if (code === 'secret_host_mismatch') {
    const h = parseHostMismatch(message)
    if (h) {
      return {
        code,
        title: base.title,
        explain: `This config calls ${h.called}, but the secret ${h.secret} is pinned to ${h.pinned}, so nothing was sent.`,
        next: `Change the Base URL to use ${h.pinned}, or save ${h.secret} again for ${h.called} on the Secrets page.`,
      }
    }
  }
  return { ...base, code: code ?? null }
}

// Why a record was set aside (Quarantine). The mapper's three reasons.
export const REASON_INFO: Record<string, { title: string; explain: string; fixable: string }> = {
  missing_required_field: {
    title: 'A required field was empty',
    explain: 'The record had no value where the mapping needs one (usually the id), so it cannot be stored.',
    fixable: 'If the field exists under another name, point the mapping at it. If the service never sends it, the record cannot be repaired.',
  },
  transform_failed: {
    title: 'A value could not be converted',
    explain: 'The mapping tried to convert a value (for example a date) and the value was not in the expected format.',
    fixable: 'Fix the transform or the date format in the mapping. A value that is simply wrong cannot be repaired.',
  },
  invalid_value: {
    title: 'A value is not one we accept',
    explain: 'The value is outside what the common schema allows (for example a status the value map does not know).',
    fixable: 'Add the value to the value map (or set a default). This is usually fixable in the config.',
  },
}

/** For these codes the raw message carries specifics the friendly text cannot (a path, a field, a status). For the rest it only repeats it. */
const MESSAGE_HAS_SPECIFICS = new Set(['api_error', 'client_error', 'bad_response', 'schema_drift', 'validation_error', 'run_failed', 'internal_error', 'conflict', 'not_found'])
export const messageAddsInfo = (code?: string | null) => !code || !ERROR_INFO[code] || MESSAGE_HAS_SPECIFICS.has(code)
