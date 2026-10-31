import { Link } from 'react-router-dom'
import type { IntegrationSummary } from '../api/client'
import { Pill } from './common'

// The alert state of an integration (D-5.3, R-17): is an email armed, counting down, sent, or did it fail to send.
// The server records what came of each alert, so "sent" means the email left the server, not just that failures were counted.

type Health = IntegrationSummary['health']
type Alert = IntegrationSummary['alert']

const when = (v: string) => new Date(v).toLocaleString()

export function AlertNote({ name, alert, health, enabled = true, compact = false }: { name: string; alert: Alert; health: Health; enabled?: boolean; compact?: boolean }) {
  const failures = health.consecutive_failures ?? 0
  if (!alert) {
    // Only nag when something is actually wrong: a healthy connection with no alert needs no note.
    return health.status === 'failing' && enabled
      ? <div className="small" style={{ marginTop: 4 }}><Pill kind="notset">no alert set</Pill> <Link to={`/integrations/${encodeURIComponent(name)}/edit`}>Add recipients</Link> to be emailed when this keeps failing.</div>
      : null
  }
  const last = alert.last_attempt
  const to = alert.to.join(', ')
  const box = { marginTop: 4, maxWidth: 260 } as const
  if (last?.outcome === 'sent') {
    return <div className="small" style={box}><Pill kind="success">alert sent</Pill> <span className="muted">to {to} at {when(last.at)}, after {last.failures} failed runs in a row. It is sent once; a successful run resets it.</span></div>
  }
  if (last?.outcome === 'failed') {
    return <div className="small" style={box} role="alert"><Pill kind="failed">alert not sent</Pill> <span className="muted">The email could not be sent{last.message ? `: ${last.message}` : ''}. Check the mail settings.</span></div>
  }
  if (last?.outcome === 'not_configured') {
    return <div className="small" style={box}><Pill kind="degraded">alert not sent</Pill> <span className="muted">The server has no email settings (SMTP), so nobody was told. Set them in <code>.env</code> and restart.</span></div>
  }
  if (failures > 0) {
    return <div className="small" style={box}><Pill kind="degraded">alert armed</Pill> <span className="muted">{failures} of {alert.after_failures} failed runs in a row. {failures >= alert.after_failures ? 'Waiting for the next run to record the alert.' : `An email goes to ${to} at ${alert.after_failures}.`}</span></div>
  }
  return compact ? null : <div className="small muted" style={box}>Alert: emails {to} after {alert.after_failures} failed runs in a row.</div>
}
