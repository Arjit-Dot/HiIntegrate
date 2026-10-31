import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { api, type TemplateSummary } from '../api/client'
import { ErrorBox, Pill } from '../components/common'

export default function Templates() {
  const [items, setItems] = useState<TemplateSummary[] | null>(null)
  const [error, setError] = useState('')
  const nav = useNavigate()
  useEffect(() => { api.listTemplates().then(r => setItems(r.items)).catch(e => setError(e.message)) }, [])

  return (
    <section>
      <div className="page-head">
        <div><h1>Templates</h1><p>Starting points for each service or record type. Pick one and the form is filled in for you.</p></div>
      </div>
      {error && <ErrorBox message={error} />}
      {items === null && !error && <div className="card card-pad muted">Loading…</div>}
      {items !== null && items.length === 0 && <div className="card card-pad muted">No templates found.</div>}
      <div className="cards">
        {(items ?? []).map(t => {
          const vars = Object.keys((t.requires?.vars as Record<string, unknown> | undefined) ?? {})
          const secrets = (t.requires?.secrets as string[] | undefined) ?? []
          return (
            <div className="card tcard" key={t.id}>
              <div className="meta"><Pill kind="trigger">{t.category}</Pill></div>
              <h2>{t.display_name}</h2>
              <p>{t.description}</p>
              {(vars.length > 0 || secrets.length > 0) && (
                <div className="muted small">
                  {vars.length > 0 && <>Asks for: {vars.map(v => <code key={v}>{v} </code>)}</>}
                  {secrets.length > 0 && <> Secret: {secrets.map(v => <code key={v}>{v} </code>)}</>}
                </div>
              )}
              <Button onClick={() => nav(`/add?template=${encodeURIComponent(t.id)}`)}>Use this template</Button>
            </div>
          )
        })}
      </div>
      <p className="note">A template is only a starting point. Saving it creates a <b>new</b> integration, and the template is never read at run time.</p>
    </section>
  )
}
