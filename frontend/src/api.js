async function apiFetch(path, options = {}) {
  const res = await fetch(path, options)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { detail = (await res.json()).detail || detail } catch (_) {}
    throw new Error(detail)
  }
  return res.json()
}

export async function uploadFile(market, file) {
  const form = new FormData()
  form.append('file', file)
  return apiFetch(`/api/upload?market=${encodeURIComponent(market)}`, {
    method: 'POST',
    body: form,
  })
}

export async function runScan(market, scanType) {
  return apiFetch(`/api/scan/${scanType}?market=${encodeURIComponent(market)}`, {
    method: 'POST',
  })
}

export function exportResults(market, scanType = 'all') {
  window.open(`/api/export?market=${encodeURIComponent(market)}&scan_type=${scanType}`, '_blank')
}

export async function fetchLiveData(market, index = null, symbols = null) {
  return apiFetch(`/api/live/fetch?market=${encodeURIComponent(market)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ index: index || null, symbols: symbols || null }),
  })
}

export async function getLiveStatus(market) {
  return apiFetch(`/api/live/status?market=${encodeURIComponent(market)}`)
}

export async function scanLiveData(market, scanType = 'all') {
  return apiFetch(`/api/live/scan?market=${encodeURIComponent(market)}&scan_type=${scanType}`, {
    method: 'POST',
  })
}

export async function compareLiveData(market) {
  return apiFetch(`/api/live/compare?market=${encodeURIComponent(market)}`)
}

export async function fetchSectors(region = 'india') {
  return apiFetch(`/api/sectors?region=${encodeURIComponent(region)}`)
}

export async function parsePortfolio(file) {
  const form = new FormData()
  form.append('file', file)
  return apiFetch('/api/portfolio/parse', { method: 'POST', body: form })
}
