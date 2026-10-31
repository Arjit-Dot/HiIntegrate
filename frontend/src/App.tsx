import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { ToastProvider } from './components/common'
import Integrations from './pages/Integrations'
import AddEdit from './pages/AddEdit'
import Placeholder from './pages/Placeholder'
import Secrets from './pages/Secrets'
import { API_BASE } from './api/client'

const NAV: [string, string][] = [
  ['/integrations', 'Integrations'], ['/add', 'Add integration'], ['/templates', 'Templates'],
  ['/results', 'Results'], ['/quarantine', 'Quarantine'], ['/runs', 'Run history'], ['/secrets', 'Secrets'],
]

export default function App() {
  return (
    <ToastProvider>
      <header className="topbar">
        <div className="brand"><div className="logo">⇄</div>Integration Platform</div>
        <nav className="nav">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'active' : '')} style={{ textDecoration: 'none' }}>
              <button type="button" tabIndex={-1} className="navlink">{label}</button>
            </NavLink>
          ))}
        </nav>
        <span className="proto" title="Set VITE_API_BASE to change it">API: {API_BASE}</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/integrations" replace />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/add" element={<AddEdit />} />
          <Route path="/integrations/:id/edit" element={<AddEdit />} />
          <Route path="/templates" element={<Placeholder title="Templates" note="Starting points for each record type." />} />
          <Route path="/results" element={<Placeholder title="Results" note="Normalized records, one table per schema." />} />
          <Route path="/quarantine" element={<Placeholder title="Quarantine" note="Records that failed the rules." />} />
          <Route path="/runs" element={<Placeholder title="Run history" note="Every scheduled, manual and test run." />} />
          <Route path="/secrets" element={<Secrets />} />
        </Routes>
      </main>
    </ToastProvider>
  )
}
