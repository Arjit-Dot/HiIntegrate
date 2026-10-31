// The only place that knows backend URLs. Point VITE_API_BASE at the Prism mock
// (http://localhost:4010) or the real backend (http://localhost:8000/api/v1).
import type { components } from '../types/api'

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? 'http://localhost:4010'

type S = components['schemas']
export type IntegrationSummary = S['IntegrationSummary']
export type Integration = S['Integration']
export type ValidateResponse = S['ValidateResponse']
export type TestResponse = S['TestResponse']
export type SecretInfo = S['SecretInfo']
export type TemplateSummary = S['TemplateSummary']
export type RunRecord = S['run_record']
export type QuarantineRecord = S['quarantine_record']
export type UnifiedUser = S['unified_user']
export type Config = Record<string, any>
export type ProposeFixResponse = S['ProposeFixResponse']
export type MappingSuggestion = S['MappingSuggestion']
export type GenerateConfigResponse = {
  yaml: string
  config?: Config
  errors: S['ValidationIssue'][]
  source?: { url: string; chars: number; truncated: boolean }
  tried?: { url: string; ok: boolean; reason: string | null }[]
  test?: {
    ran: boolean; skipped_reason?: string; action?: string; ok?: boolean; status_code?: number | null
    missing_paths: string[]; notes: string[]; filled_vars: Record<string, unknown>; corrected?: boolean; missing_before?: string[]
  }
  attempts?: { attempt: number; valid: boolean; error_count: number }[]
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message)
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'unreachable', `Cannot reach the API at ${API_BASE}. Is the mock or backend running?`)
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  const data = text ? JSON.parse(text) : undefined
  if (!res.ok) {
    const e = data?.error
    throw new ApiError(res.status, e?.code ?? 'error', e?.message ?? `Request failed (${res.status})`, e?.details)
  }
  return data as T
}

const qs = (p: Record<string, string | number | undefined>) => {
  const q = new URLSearchParams()
  Object.entries(p).forEach(([k, v]) => v !== undefined && v !== '' && q.set(k, String(v)))
  return q.toString()
}

export const api = {
  health: () => call<{ status: string }>('GET', '/health'),
  listIntegrations: (p: { q?: string; category?: string; status?: string } = {}) => {
    const qs = new URLSearchParams()
    Object.entries({ ...p, limit: '200' }).forEach(([k, v]) => v && qs.set(k, v))
    return call<{ items: IntegrationSummary[]; total: number }>('GET', `/integrations?${qs}`)
  },
  getIntegration: (id: string) => call<Integration>('GET', `/integrations/${encodeURIComponent(id)}`),
  validate: (config: Config) => call<ValidateResponse>('POST', '/integrations/validate', config),
  create: (config: Config) => call<Integration>('POST', '/integrations', config),
  replace: (id: string, config: Config) => call<Integration>('PUT', `/integrations/${encodeURIComponent(id)}`, config),
  setEnabled: (id: string, enabled: boolean) =>
    call<IntegrationSummary>('PATCH', `/integrations/${encodeURIComponent(id)}/enabled`, { enabled }),
  test: (id: string, action: string, inputs?: Record<string, unknown>) =>
    call<TestResponse>('POST', `/integrations/${encodeURIComponent(id)}/test`, { action, inputs }),
  /** AI mode (D-14): a service name (the AI finds the docs), a documentation url, or attached text in; a draft config out. Nothing is saved. */
  generateConfig: (b: { service?: string; url?: string; text?: string }) => call<GenerateConfigResponse>('POST', '/ai/generate-config', b),
  /** AI summary of the stored records (D-14). Nothing is saved; 501 when the server has no LLM_API_KEY. */
  summarize: (b: { target?: 'user' | 'device' | 'alert'; source?: string }) => call<{ summary: string }>('POST', '/ai/summarize', b),
  /** AI propose-fix (D-14): a dry run. Nothing is saved; a person applies the fix with `replace`. 501 without LLM_API_KEY. */
  proposeFix: (b: { kind: 'quarantine' | 'run_failure'; integration: string; action: string; run_id?: string }) =>
    call<ProposeFixResponse>('POST', '/ai/propose-fix', b),
  /** AI mapping suggestions (D-14): a sample in, a checked path per field out. With `mapping` no model is called. Nothing is saved. */
  suggestMapping: (b: { target_schema: 'user' | 'device' | 'alert'; sample: unknown; mapping?: Record<string, { path: string; transform?: string | null; value_map?: Record<string, string> | null }> }) =>
    call<MappingSuggestion>('POST', '/ai/suggest-mapping', b),
  listTemplates: () => call<{ items: TemplateSummary[] }>('GET', '/templates'),
  getTemplate: (id: string) => call<{ id: string; config: Config; yaml: string }>('GET', `/templates/${encodeURIComponent(id)}`),
  listResults: (p: { target: string; source?: string; limit?: number; offset?: number }) =>
    call<{ items: Record<string, unknown>[]; total: number; limit: number; offset: number }>('GET', `/results?${qs(p)}`),
  listUnifiedUsers: (p: { source?: string; limit?: number; offset?: number }) =>
    call<{ items: UnifiedUser[]; total: number; limit: number; offset: number }>('GET', `/users/unified?${qs(p)}`),
  listQuarantine: (p: { reason?: string; target_schema?: string; source?: string; limit?: number; offset?: number }) =>
    call<{ items: QuarantineRecord[]; total: number; limit: number; offset: number }>('GET', `/quarantine?${qs(p)}`),
  /** Every quarantined record with the same filters, as the JSON text of the file. */
  exportQuarantine: async (p: { reason?: string; target_schema?: string; source?: string }): Promise<string> => {
    let res: Response
    try { res = await fetch(`${API_BASE}/quarantine/export?${qs(p)}`) }
    catch { throw new ApiError(0, 'unreachable', `Cannot reach the API at ${API_BASE}. Is the mock or backend running?`) }
    if (!res.ok) throw new ApiError(res.status, 'export_failed', `Export failed (${res.status})`)
    return res.text()
  },
  listRuns: (p: { status?: string; integration?: string; limit?: number; offset?: number }) =>
    call<{ items: RunRecord[]; total: number; limit: number; offset: number }>('GET', `/runs?${qs(p)}`),
  /** Run one action now. A lookup answers 200 with the mapped record; a pull answers 202 with a run id. */
  runAction: async (id: string, action: string, inputs?: Record<string, unknown>) => {
    let res: Response
    try {
      res = await fetch(`${API_BASE}/integrations/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}/run`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(inputs ? { inputs } : {}),
      })
    } catch { throw new ApiError(0, 'unreachable', `Cannot reach the API at ${API_BASE}. Is the mock or backend running?`) }
    const text = await res.text()
    const data = text ? JSON.parse(text) : undefined
    if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? 'error', data?.error?.message ?? `Request failed (${res.status})`, data?.error?.details)
    return { status: res.status, runId: res.headers.get('X-Run-Id') ?? (data?.run_id as string | undefined) ?? null, body: data as Record<string, unknown> }
  },
  listSecrets: () => call<{ items: SecretInfo[] }>('GET', '/secrets'),
  setSecret: (name: string, value: string, host: string) =>
    call<void>('PUT', `/secrets/${encodeURIComponent(name)}`, { value, host }),
}
