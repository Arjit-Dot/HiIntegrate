import { useEffect, useRef, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
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

// The side menu: where each page lives, and one line saying what it is for.
const NAV: [path: string, label: string, hint: string][] = [
  ['/integrations', 'Integrations', 'Your connected tools and their health'],
  ['/add', 'Add integration', 'Connect a new service'],
  ['/templates', 'Templates', 'Ready-made starting points'],
  ['/results', 'Results', 'People, devices and alerts we pulled'],
  ['/quarantine', 'Quarantine', 'Records that failed the rules'],
  ['/runs', 'Run history', 'Every run and how it went'],
  ['/secrets', 'Secrets', 'Keys and passwords, kept by name'],
]

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [menuOpen, setMenuOpen] = useState(false)
  const brandRef = useRef<HTMLButtonElement>(null)
  const firstLinkRef = useRef<HTMLAnchorElement>(null)
  const { pathname } = useLocation()
  const here = NAV.find(([path]) => pathname === path || pathname.startsWith(path + '/'))
  // undefined: still checking the saved sign-in. null: nobody is signed in.
  const [user, setUser] = useState<string | null | undefined>(getToken() ? undefined : null)

  useEffect(() => {
    if (getToken()) auth.me().then(r => setUser(r.username)).catch(() => setUser(null))
    const out = () => setUser(null)   // the server said the sign-in ended
    window.addEventListener(SESSION_EXPIRED, out)
    return () => window.removeEventListener(SESSION_EXPIRED, out)
  }, [])

  // The side menu: Escape closes it, the page behind does not scroll while it is open, and focus moves in and back out.
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeMenu() }
    window.addEventListener('keydown', onKey)
    const before = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    firstLinkRef.current?.focus()
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = before }
  }, [menuOpen])
  useEffect(() => { if (!user) setMenuOpen(false) }, [user])
  function closeMenu() { setMenuOpen(false); brandRef.current?.focus() }

  async function signOut() {
    await auth.signOut()
    setUser(null)
  }

  return (
    <ToastProvider>
      <header className="topbar">
        {user
          ? <button type="button" ref={brandRef} className="brand brand-btn" aria-expanded={menuOpen} aria-controls="sidemenu"
              onClick={() => setMenuOpen(o => !o)} title="Open the menu">
              <div className="logo">⇄</div>HiIntegrate<span className="burger" aria-hidden="true">☰</span><span className="sr-only">Menu</span>
            </button>
          : <div className="brand"><div className="logo">⇄</div>HiIntegrate</div>}
        {user && here && <span className="here" aria-label="Current page">{here[1]}</span>}
        {user && <div style={{ flex: 1 }} />}
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
      {user && <>
        <div className={menuOpen ? 'sidemenu-bg open' : 'sidemenu-bg'} onClick={closeMenu} aria-hidden="true" />
        <aside id="sidemenu" className={menuOpen ? 'sidemenu open' : 'sidemenu'} aria-label="Main menu" aria-hidden={!menuOpen}>
          <div className="sidemenu-head">
            <div className="brand"><div className="logo">⇄</div>HiIntegrate</div>
            <button type="button" className="sidemenu-close" onClick={closeMenu} aria-label="Close the menu">✕</button>
          </div>
          <nav className="sidemenu-nav">
            {NAV.map(([to, label, hint], i) => (
              <NavLink key={to} to={to} ref={i === 0 ? firstLinkRef : undefined} onClick={() => setMenuOpen(false)} tabIndex={menuOpen ? 0 : -1}
                className={({ isActive }) => (isActive ? 'sidelink active' : 'sidelink')}>
                <span className="sidelink-label">{label}</span>
                <span className="sidelink-hint">{hint}</span>
              </NavLink>
            ))}
          </nav>
          <div className="sidemenu-foot"><span className="muted small">Signed in as</span> <b>{user}</b></div>
        </aside>
      </>}
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
