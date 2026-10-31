import { Button } from '@/components/ui/button'

export const PAGE_SIZE = 50

/** Previous / next for a paged list. Shows nothing when everything fits on one page. */
export function Pager({ offset, total, onChange }: { offset: number; total: number; onChange: (offset: number) => void }) {
  if (total <= PAGE_SIZE) return null
  const to = Math.min(offset + PAGE_SIZE, total)
  return (
    <div className="inline" style={{ justifyContent: 'center', marginTop: 12 }}>
      <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
      <span className="muted small">{offset + 1}–{to} of {total.toLocaleString()}</span>
      <Button variant="secondary" size="sm" disabled={to >= total} onClick={() => onChange(offset + PAGE_SIZE)}>Next</Button>
    </div>
  )
}
