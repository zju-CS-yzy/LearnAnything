/**
 * Browser <img> requests cannot attach Authorization headers. Add the
 * current auth token to same-origin media URLs for server-side validation.
 */
export function withMediaAuth(url) {
  if (!url || !url.includes('/api/')) return url
  if (url.startsWith('http') && typeof window !== 'undefined' && !url.startsWith(window.location.origin)) {
    return url
  }
  let token = ''
  try {
    token = localStorage.getItem('la_auth_token') || ''
  } catch {
    token = ''
  }
  if (!token || url.includes('access_token=')) return url
  return `${url}${url.includes('?') ? '&' : '?'}access_token=${encodeURIComponent(token)}`
}
