import { useCallback, useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

function current(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

// The <html> class is the single source of truth, so every component using the hook stays in sync.
function subscribe(cb: () => void) {
  const obs = new MutationObserver(cb)
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  return () => obs.disconnect()
}

/** Dark mode toggle. The initial class is set by the inline script in index.html (no flash on load). */
export function useTheme(): [Theme, () => void] {
  const theme = useSyncExternalStore(subscribe, current)
  const toggle = useCallback(() => {
    const next: Theme = current() === 'dark' ? 'light' : 'dark'
    document.documentElement.classList.toggle('dark', next === 'dark')
    try { localStorage.setItem('theme', next) } catch { /* storage unavailable */ }
  }, [])
  return [theme, toggle]
}
