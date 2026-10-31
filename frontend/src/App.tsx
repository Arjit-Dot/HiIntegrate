import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { ToastProvider } from './components/common'
import Integrations from './pages/Integrations'
import AddEdit from './pages/AddEdit'
import Templates from './pages/Templates'
import Results from './pages/Results'
import Quarantine from './pages/Quarantine'
import Runs from './pages/Runs'
import Secrets from './pages/Secrets'
import { API_BASE } from './api/client'
import { useTheme } from './lib/theme'

const NAV: [string, string][] = [
  ['/integrations', 'Integrations'], ['/add', 'Add integration'], ['/templates', 'Templates'],
  ['/results', 'Results'], ['/quarantine', 'Quarantine'], ['/runs', 'Run history'], ['/secrets', 'Secrets'],
]

export default function App() {
  const [theme, toggleTheme] = useTheme()
  return (
    <ToastProvider>
      <header className="topbar">
        <div className="brand"><div className="logo">⇄</div>HiIntegrate</div>
        <nav className="nav">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'active' : '')} style={{ textDecoration: 'none' }}>
              <button type="button" tabIndex={-1} className="navlink">{label}</button>
            </NavLink>
          ))}
        </nav>
        <span className="proto" title="Set VITE_API_BASE to change it">API: {API_BASE}</span>
        <button type="button" className="theme-toggle" onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={theme === 'dark' ? 'Light mode' : 'Dark mode'}>{theme === 'dark' ? '☀' : '☾'}</button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/integrations" replace />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/add" element={<AddEdit />} />
          <Route path="/integrations/:id/edit" element={<AddEdit />} />
          <Route path="/templates" element={<Templates />} />
          <Route path="/results" element={<Results />} />
          <Route path="/quarantine" element={<Quarantine />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/secrets" element={<Secrets />} />
        </Routes>
      </main>
    </ToastProvider>
  )
}
