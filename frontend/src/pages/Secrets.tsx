import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { api, ApiError, type SecretInfo } from '../api/client'
import { ErrorBox, Pill, useToast } from '../components/common'

// Same rule as the API: lowercase, no scheme, no path, no port.
const HOST_RE = /^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$/

export default function Secrets() {
  const [items, setItems] = useState<SecretInfo[] | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(() => {
    api.listSecrets().then(r => { setItems(r.items); setError('') }).catch(e => setError(e.message))
  }, [])
  useEffect(load, [load])

  return (
    <section>
      <div className="page-head">
        <div><h1>Secrets</h1><p>Keys and passwords are kept by name. A value can be set or replaced, and never shown again. Each one is pinned to the host it may be sent to.</p></div>
      </div>
      {error && <ErrorBox message={error} />}
      <div className="card tablewrap">
        <table>
          <thead><tr><th>Name</th><th>Status</th><th>Pinned host</th><th>Updated</th><th style={{ width: '44%' }}>Set or replace value</th></tr></thead>
          <tbody>
            {items === null && !error && <tr><td colSpan={5} className="muted">Loading…</td></tr>}
            {items !== null && items.length === 0 && <tr><td colSpan={5} className="muted">No secrets yet. Add an integration to create one, or set one from its form.</td></tr>}
            {(items ?? []).map(s => <SecretRow key={s.name} secret={s} onSaved={load} />)}
          </tbody>
        </table>
      </div>
      <p className="note">Configs refer to a secret by its name only. Values are stored encrypted and are hidden in logs and responses. The platform refuses to send a secret to any host other than the one it is pinned to.</p>
    </section>
  )
}

function SecretRow({ secret, onSaved }: { secret: SecretInfo; onSaved: () => void }) {
  const [value, setValue] = useState('')
  const [host, setHost] = useState(secret.host ?? '')
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  async function save() {
    const h = host.trim().toLowerCase()
    if (!value) { toast('Enter the value first.'); return }
    if (!HOST_RE.test(h)) { toast('Enter the host only, such as api.github.com (no https://, path or port).'); return }
    setBusy(true)
    try {
      await api.setSecret(secret.name, value, h)
      setValue('')   // never keep the value in the page
      toast(`${secret.name} ${secret.set ? 'replaced' : 'set'} and pinned to ${h}`)
      onSaved()
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) toast(`Secret store not available yet. Set SECRET_${secret.name.toUpperCase()} in .env.`)
      else toast(e instanceof Error ? e.message : 'Could not save the secret')
    } finally { setBusy(false) }
  }

  return (
    <tr>
      <td className="mono">{secret.name}</td>
      <td><Pill kind={secret.set ? 'set' : 'notset'}>{secret.set ? 'set' : 'not set'}</Pill></td>
      <td className="mono small">{secret.host ?? <span className="muted">not pinned</span>}</td>
      <td className="small">{secret.updated_at ? new Date(secret.updated_at).toLocaleString() : ''}</td>
      <td>
        <div className="inline">
          <input type="password" autoComplete="new-password" placeholder={secret.set ? 'New value' : 'Value'} value={value} onChange={e => setValue(e.target.value)} />
          <input type="text" className="mono" style={{ maxWidth: 190 }} placeholder="host, e.g. api.github.com" value={host} onChange={e => setHost(e.target.value)} />
          <Button size="sm" disabled={busy} onClick={save}>{secret.set ? 'Replace' : 'Set'}</Button>
        </div>
      </td>
    </tr>
  )
}
