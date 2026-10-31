// The sign-in (D-18). The token is kept in localStorage and sent in the X-Session-Token header.
// Only the server decides who a token belongs to; the page just remembers it.
const KEY = 'session_token'
export const SESSION_EXPIRED = 'session-expired'

export const getToken = (): string => {
  try { return localStorage.getItem(KEY) ?? '' } catch { return '' }
}
export const setToken = (token: string) => {
  try { localStorage.setItem(KEY, token) } catch { /* storage unavailable: the sign-in lasts until reload */ }
}
export const clearToken = () => {
  try { localStorage.removeItem(KEY) } catch { /* nothing to clear */ }
}
/** Called when the server answers 401 to a signed-in request: forget the token and tell the app to show the sign-in page. */
export const expireSession = () => {
  if (!getToken()) return
  clearToken()
  window.dispatchEvent(new Event(SESSION_EXPIRED))
}
