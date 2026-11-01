import { useEffect, useRef, useState, type ReactNode, type CSSProperties } from 'react'
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

// Small line icons for the side menu (24x24, drawn with strokes).
const ICONS: Record<string, ReactNode> = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /></>,
  plus: <><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="16" /><line x1="8" y1="12" x2="16" y2="12" /></>,
  layout: <><rect x="3" y="3" width="18" height="18" rx="2" /><line x1="3" y1="9" x2="21" y2="9" /><line x1="9" y1="21" x2="9" y2="9" /></>,
  users: <><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></>,
  alert: <><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>,
  clock: <><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></>,
  key: <><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" /></>,
}
function Icon({ name }: { name: string }) {
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[name]}</svg>
}

// The side menu: where each page lives, an icon, a colour, and one line saying what it is for.
const NAV: [path: string, label: string, hint: string, icon: string, tint: string][] = [
  ['/integrations', 'Integrations', 'Your connected tools and their health', 'grid', '#6366f1'],
  ['/add', 'Add integration', 'Connect a new service', 'plus', '#16a34a'],
  ['/templates', 'Templates', 'Ready-made starting points', 'layout', '#8b5cf6'],
  ['/results', 'Results', 'People, devices and alerts we pulled', 'users', '#0ea5e9'],
  ['/quarantine', 'Quarantine', 'Records that failed the rules', 'alert', '#f59e0b'],
  ['/runs', 'Run history', 'Every run and how it went', 'clock', '#14b8a6'],
  ['/secrets', 'Secrets', 'Keys and passwords, kept by name', 'key', '#e11d48'],
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
            {NAV.map(([to, label, hint, icon, tint], i) => (
              <NavLink key={to} to={to} ref={i === 0 ? firstLinkRef : undefined} onClick={() => setMenuOpen(false)} tabIndex={menuOpen ? 0 : -1}
                style={{ '--tint': tint } as CSSProperties}
                className={({ isActive }) => (isActive ? 'sidelink active' : 'sidelink')}>
                <span className="sidelink-icon"><Icon name={icon} /></span>
                <span className="sidelink-text">
                  <span className="sidelink-label">{label}</span>
                  <span className="sidelink-hint">{hint}</span>
                </span>
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
