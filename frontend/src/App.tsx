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

const NAV: [string, string][] = [
  ['/integrations', 'Integrations'], ['/add', 'Add integration'], ['/templates', 'Templates'],
  ['/results', 'Results'], ['/quarantine', 'Quarantine'], ['/runs', 'Run history'], ['/secrets', 'Secrets'],
]

export default function App() {
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
