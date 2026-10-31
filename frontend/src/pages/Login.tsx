import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { auth, ApiError } from '../api/client'
import { ErrorBox } from '../components/common'

// Sign in or create an account (D-18). Each person has their own integrations, records and secrets.
export default function Login({ onSignedIn }: { onSignedIn: (username: string) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setError('')
    try { onSignedIn(await auth.signIn(mode, username.trim(), password)) }
    catch (err) { setError(err instanceof ApiError || err instanceof Error ? err.message : 'Could not sign in') }
    finally { setBusy(false) }
  }

  const creating = mode === 'register'
  return (
    <section style={{ maxWidth: 380, margin: '8vh auto 0' }}>
      <div className="page-head"><div>
        <h1>{creating ? 'Create an account' : 'Sign in'}</h1>
        <p>{creating ? 'Your integrations, records and secrets belong to you alone.' : 'Your integrations, records and secrets are private to your account.'}</p>
      </div></div>
      <form className="card card-pad" onSubmit={submit}>
        {error && <ErrorBox message={error} />}
        <div style={{ marginBottom: 12 }}>
          <label htmlFor="username">Username</label>
          <input id="username" type="text" autoComplete="username" autoFocus value={username} onChange={e => setUsername(e.target.value)} />
          {creating && <div className="hint">3 to 32 characters: letters, digits, dot, dash or underscore.</div>}
        </div>
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete={creating ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)} />
          {creating && <div className="hint">At least 8 characters.</div>}
        </div>
        <Button type="submit" disabled={busy || !username || !password} style={{ width: '100%' }}>
          {busy ? 'Please wait…' : creating ? 'Create account' : 'Sign in'}
        </Button>
      </form>
      <p className="note">
        {creating ? 'Already have an account? ' : 'New here? '}
        <a href="#" onClick={e => { e.preventDefault(); setMode(creating ? 'login' : 'register'); setError('') }}>{creating ? 'Sign in' : 'Create an account'}</a>
      </p>
    </section>
  )
}
