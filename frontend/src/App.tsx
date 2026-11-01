import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { ToastProvider } from './components/common'
import Integrations from './pages/Integrations'
import AddEdit from './pages/AddEdit'
import Templates from './pages/Templates'
import Results from './pages/Results'
import Quarantine from './pages/Quarantine'
import Runs from './pages/Runs'
import Secrets from './pages/Secrets'
import Login from './pages/Login'
import { API_BASE, auth } from './api/client'
import { SESSION_EXPIRED, getToken } from './api/session'
import { useTheme } from './lib/theme'

// The pages, in a row across the top bar.
const NAV: [path: string, label: string][] = [
  ['/integrations', 'Integrations'], ['/add', 'Add integration'], ['/templates', 'Templates'],
  ['/results', 'Results'], ['/quarantine', 'Quarantine'], ['/runs', 'Run history'], ['/secrets', 'Secrets'],
]

export default function App() {
  const [theme, toggleTheme] = useTheme()
  // undefined: still checking the saved sign-in. null: nobody is signed in.
  const [user, setUser] = useState<string | null | undefined>(getToken() ? undefined : null)

  useEffect(() => {
    if (getToken()) auth.me().then(r => setUser(r.username)).catch(() => setUser(null))
    const out = () => setUser(null)   // the server said the sign-in ended
    window.addEventListener(SESSION_EXPIRED, out)
    return () => window.removeEventListener(SESSION_EXPIRED, out)
  }, [])

  async function signOut() {
    await auth.signOut()
    setUser(null)
  }

  return (
    <ToastProvider>
      <header className="topbar">
        <div className="brand"><div className="logo">⇄</div>HiIntegrate</div>
        {user && <nav className="nav">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'active' : '')} style={{ textDecoration: 'none' }}>
              <button type="button" tabIndex={-1} className="navlink">{label}</button>
            </NavLink>
          ))}
        </nav>}
        {!user && <div style={{ flex: 1 }} />}
        <span className="proto" title="Set VITE_API_BASE to change it">API: {API_BASE}</span>
        {user && <>
          <span className="small muted" title="Signed in">{user}</span>
          <button type="button" className="btn secondary small" onClick={signOut}>Sign out</button>
        </>}
        <button type="button" className="theme-toggle" onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={theme === 'dark' ? 'Light mode' : 'Dark mode'}>{theme === 'dark' ? '☀' : '☾'}</button>
      </header>
      <main>
        {user === undefined ? <p className="muted">Checking your sign-in…</p>
        : user === null ? <Login onSignedIn={setUser} />
        : <Routes>
          <Route path="/" element={<Navigate to="/integrations" replace />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/add" element={<AddEdit />} />
          <Route path="/integrations/:id/edit" element={<AddEdit />} />
          <Route path="/templates" element={<Templates />} />
          <Route path="/results" element={<Results />} />
          <Route path="/quarantine" element={<Quarantine />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/secrets" element={<Secrets />} />
        </Routes>}
      </main>
    </ToastProvider>
  )
}
