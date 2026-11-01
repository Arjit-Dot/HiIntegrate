import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { api, ApiError, type SecretInfo } from '../api/client'
import { ErrorBox, Pill, useToast } from '../components/common'
import { Banner } from '../components/modal-parts'

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
        <div><h1>Secrets</h1><p>The keys and passwords your integrations use to sign in to other services.</p></div>
      </div>
      <div style={{ marginBottom: 18 }}>
        <Banner tone="info" title="Write-only, encrypted, and pinned to one host">
          You can set or replace a value here, but it is never shown again, not even to you. Each secret can only be sent to the host shown next to it: if a config calls any other host, the request is blocked and nothing is sent.
        </Banner>
      </div>
      {error && <ErrorBox message={error} />}
      <div className="card tablewrap">
        <table>
          <thead><tr><th>Name</th><th>Status</th><th>Pinned host</th><th>Updated</th><th style={{ width: '44%' }}>Set or replace the value</th></tr></thead>
          <tbody>
            {items === null && !error && <tr><td colSpan={5} className="muted">Loading…</td></tr>}
            {items !== null && items.length === 0 && <tr><td colSpan={5} className="muted">No secrets yet. Add an integration and set its key in the form, or use Add a secret below.</td></tr>}
            {(items ?? []).map(s => <SecretRow key={s.name} secret={s} onSaved={load} />)}
          </tbody>
        </table>
      </div>
      <NewSecret onSaved={load} />
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
    if (!value) { toast(`Type the new value for ${secret.name} first.`); return }
    if (!HOST_RE.test(h)) { toast('Enter the host only, such as api.github.com: no https://, no path and no port.'); return }
    setBusy(true)
    try {
      await api.setSecret(secret.name, value, h)
      setValue('')   // never keep the value in the page
      toast(`${secret.name} ${secret.set ? 'replaced' : 'saved'}. It can now only be sent to ${h}.`)
      onSaved()
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) toast(`Secret store not available yet. Set SECRET_${secret.name.toUpperCase()} in .env.`)
      else toast(e instanceof Error ? `Could not save ${secret.name}: ${e.message}` : `Could not save ${secret.name}.`)
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
          <Button size="sm" disabled={busy} onClick={save} title={`Encrypts the value and pins ${secret.name} to the host in the box`}>{busy ? 'Saving…' : secret.set ? 'Replace value' : 'Set value'}</Button>
        </div>
      </td>
    </tr>
  )
}

const NAME_RE = /^[A-Za-z0-9_]{1,64}$/

// A secret that no config refers to yet, such as the mail password for alert emails (name it smtp_password).
function NewSecret({ onSaved }: { onSaved: () => void }) {
  const [name, setName] = useState('')
  const [value, setValue] = useState('')
  const [host, setHost] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  async function save() {
    const n = name.trim()
    const h = host.trim().toLowerCase()
    if (!NAME_RE.test(n)) { toast('A secret name uses letters, digits and underscores only, for example smtp_password.'); return }
    if (!value) { toast('Type the secret value first.'); return }
    if (!HOST_RE.test(h)) { toast('Enter the host only, such as smtp.gmail.com: no https://, no path and no port.'); return }
    setBusy(true)
    try {
      await api.setSecret(n, value, h)
      setValue(''); setName(''); setHost('')   // never keep the value in the page
      toast(`${n} saved. It can now only be sent to ${h}.`)
      onSaved()
    } catch (e) {
      toast(e instanceof Error ? `Could not save ${n}: ${e.message}` : `Could not save ${n}.`)
    } finally { setBusy(false) }
  }

  return (
    <div className="card" style={{ marginTop: 16, padding: 16 }}>
      <h2 style={{ marginTop: 0 }}>Add a secret</h2>
      <p className="small muted">
        For a key that no integration uses yet. For alert emails, name it <code>smtp_password</code>, give the mail password, and pin it to the
        mail server (the same host as <code>SMTP_HOST</code>, for example <code>smtp.gmail.com</code>). The password is sent only to that host.
      </p>
      <div className="inline">
        <input type="text" className="mono" style={{ maxWidth: 190 }} placeholder="name, e.g. smtp_password" value={name} onChange={e => setName(e.target.value)} />
        <input type="password" autoComplete="new-password" placeholder="Value (never shown again)" value={value} onChange={e => setValue(e.target.value)} />
        <input type="text" className="mono" style={{ maxWidth: 190 }} placeholder="host, e.g. smtp.gmail.com" value={host} onChange={e => setHost(e.target.value)} />
        <Button size="sm" disabled={busy} onClick={save} title="Encrypts the value and pins the name to the host">{busy ? 'Saving…' : 'Save secret'}</Button>
      </div>
    </div>
  )
}
