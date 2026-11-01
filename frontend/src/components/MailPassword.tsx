import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { api, type SecretInfo } from '../api/client'
import { Pill, useToast } from './common'

const HOST_RE = /^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$/

// Shown under "Alert recipients": the mail password the server uses to send the alert email. It is the account's secret
// `smtp_password`, stored encrypted and pinned to the mail server, so it is asked for here instead of in a file.
export function MailPassword() {
  const [secret, setSecret] = useState<SecretInfo | null | undefined>(undefined)   // undefined: loading, null: not set
  const [value, setValue] = useState('')
  const [host, setHost] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  const load = useCallback(() => {
    api.listSecrets().then(r => {
      const s = r.items.find(x => x.name === 'smtp_password') ?? null
      setSecret(s); if (s?.host) setHost(h => h || s.host!)
    }).catch(() => setSecret(null))
  }, [])
  useEffect(load, [load])

  async function save() {
    const h = host.trim().toLowerCase()
    if (!value) { toast('Enter the mail password first.'); return }
    if (!HOST_RE.test(h)) { toast('Enter the mail server only, such as smtp.gmail.com (no https://, path or port).'); return }
    setBusy(true)
    try {
      await api.setSecret('smtp_password', value, h)
      setValue('')   // never keep the value in the page
      toast(`Mail password saved (encrypted) and pinned to ${h}`)
      load()
    } catch (e) { toast(e instanceof Error ? e.message : 'Could not save the mail password') }
    finally { setBusy(false) }
  }

  return (
    <div className="full card" style={{ padding: 12 }}>
      <label>Mail password for the alert email{' '}
        {secret === undefined ? null : secret
          ? <Pill kind="set">saved, pinned to {secret.host}</Pill>
          : <Pill kind="notset">not set: the email cannot log in to the mail server</Pill>}
      </label>
      <div className="inline">
        <input type="password" autoComplete="new-password" placeholder={secret ? 'New password (leave empty to keep the saved one)' : 'SMTP password (a Gmail app password)'}
          value={value} onChange={e => setValue(e.target.value)} />
        <input type="text" className="mono" style={{ maxWidth: 210 }} placeholder="mail server, e.g. smtp.gmail.com" value={host} onChange={e => setHost(e.target.value)} />
        <Button type="button" size="sm" disabled={busy} onClick={save}>Save mail password</Button>
      </div>
      <div className="hint">Stored encrypted as the secret <code>smtp_password</code>, never shown again, and sent only to that mail server.</div>
    </div>
  )
}
