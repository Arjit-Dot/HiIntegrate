export default function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <section>
      <div className="page-head"><div><h1>{title}</h1><p>{note}</p></div></div>
      <div className="card card-pad muted">Built in Phase 2 (see roadmap.md).</div>
    </section>
  )
}
