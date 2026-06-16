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

export async function fetchLiveData(market, index = null, symbols = null, portfolioMarket = null) {
  return apiFetch(`/api/live/fetch?market=${encodeURIComponent(market)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      index: index || null,
      symbols: symbols || null,
      portfolio_market: portfolioMarket || null,
    }),
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

export async function parsePortfolio(file, market = 'india') {
  const form = new FormData()
  form.append('file', file)
  return apiFetch(`/api/portfolio/parse?market=${encodeURIComponent(market)}`, {
    method: 'POST',
    body: form,
  })
}

export async function fetchDbStatus() {
  return apiFetch('/api/db/status')
}

export async function searchInstruments(market, q) {
  return apiFetch(`/api/db/search?market=${encodeURIComponent(market)}&q=${encodeURIComponent(q)}`)
}

export async function seedMarket(market, force = false) {
  return apiFetch(`/api/db/seed?market=${encodeURIComponent(market)}&force=${force}`, {
    method: 'POST',
  })
}

// ── File workspace ────────────────────────────────────────────────────────────
export async function listFiles() {
  return apiFetch('/api/files')
}

export async function uploadWorkspaceFile(file, label = '') {
  const form = new FormData()
  form.append('file', file)
  const qs = label ? `?label=${encodeURIComponent(label)}` : ''
  return apiFetch(`/api/files/upload${qs}`, { method: 'POST', body: form })
}

export async function deleteFile(fileId) {
  return apiFetch(`/api/files/${fileId}`, { method: 'DELETE' })
}

export async function previewFile(fileId, rows = 20) {
  return apiFetch(`/api/files/${fileId}/preview?rows=${rows}`)
}

export async function analyseFile(fileId, analysis, market = 'india', scanType = null) {
  let qs = `analysis=${encodeURIComponent(analysis)}&market=${encodeURIComponent(market)}`
  if (scanType) qs += `&scan_type=${encodeURIComponent(scanType)}`
  return apiFetch(`/api/files/${fileId}/analyse?${qs}`, { method: 'POST' })
}

export async function fetchGeographyStatus() {
  return apiFetch('/api/db/geography')
}

export async function fetchDailyScan(markets = 'india,us,europe,japan,korea,china,hong_kong,canada', scans = 'darvas,piotroski') {
  return apiFetch(
    `/api/db/daily/scan?markets=${encodeURIComponent(markets)}&scans=${encodeURIComponent(scans)}`,
    { method: 'POST' },
  )
}

export async function fetchStockNews(ticker, market = 'india', limit = 8) {
  return apiFetch(`/api/news/stock/${encodeURIComponent(ticker)}?market=${encodeURIComponent(market)}&limit=${limit}`)
}

export async function fetchSectorNews(sector, market = 'all', limit = 10) {
  return apiFetch(`/api/news/sector?name=${encodeURIComponent(sector)}&market=${encodeURIComponent(market)}&limit=${limit}`)
}

export async function fetchPortfolioHistory(market, holdings) {
  return apiFetch('/api/portfolio/history', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ market, holdings }),
  })
}

// ── Event-driven news alerts ──────────────────────────────────────────────────

export async function addToAlertWatchlist(tickers, market = 'india') {
  return apiFetch('/api/alerts/portfolio', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers, market }),
  })
}

export async function getAlertWatchlist() {
  return apiFetch('/api/alerts/portfolio')
}

export async function removeFromAlertWatchlist(ticker) {
  return apiFetch(`/api/alerts/portfolio/${encodeURIComponent(ticker)}`, { method: 'DELETE' })
}

export async function getLatestAlerts(limit = 20) {
  return apiFetch(`/api/alerts/latest?limit=${limit}`)
}

export async function triggerAlertFetch(ticker, market = 'india') {
  return apiFetch(`/api/alerts/trigger/${encodeURIComponent(ticker)}?market=${encodeURIComponent(market)}`, {
    method: 'POST',
  })
}
