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
export type Config = Record<string, any>

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
  listSecrets: () => call<{ items: SecretInfo[] }>('GET', '/secrets'),
  setSecret: (name: string, value: string, host: string) =>
    call<void>('PUT', `/secrets/${encodeURIComponent(name)}`, { value, host }),
}
