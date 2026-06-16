import { useCallback, useEffect, useRef, useState } from 'react'

const BASE_URL = 'http://localhost:8000'

const EVENT_META = {
  PRICE_UP:       { label: '↑ Price Up',       color: 'bg-green-900 text-green-300 border-green-700' },
  PRICE_DOWN:     { label: '↓ Price Down',      color: 'bg-red-900 text-red-300 border-red-700' },
  RSI_OVERBOUGHT: { label: 'RSI Overbought',    color: 'bg-orange-900 text-orange-300 border-orange-700' },
  RSI_OVERSOLD:   { label: 'RSI Oversold',      color: 'bg-blue-900 text-blue-300 border-blue-700' },
  VOLUME_SURGE:   { label: '⚡ Volume Surge',   color: 'bg-purple-900 text-purple-300 border-purple-700' },
  HIGH_52W:       { label: '🏔 52W High',        color: 'bg-emerald-900 text-emerald-300 border-emerald-700' },
  LOW_52W:        { label: '🕳 52W Low',          color: 'bg-rose-900 text-rose-300 border-rose-700' },
  MANUAL:         { label: '🔍 Manual Fetch',    color: 'bg-gray-800 text-gray-300 border-gray-600' },
}

const MARKET_CURRENCY = {
  india: '₹', us: '$', europe: '€', japan: '¥', korea: '₩', china: '¥',
}

function EventBadge({ type }) {
  const meta = EVENT_META[type] || { label: type, color: 'bg-gray-800 text-gray-300 border-gray-600' }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border ${meta.color}`}>
      {meta.label}
    </span>
  )
}

function EventDetail({ type, data, market }) {
  const cur = MARKET_CURRENCY[market] || ''
  if (!data || Object.keys(data).length === 0) return null

  const items = []
  if (data.price != null)       items.push(`Price: ${cur}${data.price}`)
  if (data.prev_close != null)  items.push(`Prev close: ${cur}${data.prev_close}`)
  if (data.pct_change != null)  items.push(`Move: ${data.pct_change > 0 ? '+' : ''}${data.pct_change}%`)
  if (data.rsi != null)         items.push(`RSI: ${data.rsi}`)
  if (data.volume != null)      items.push(`Vol: ${(data.volume / 1e6).toFixed(2)}M`)
  if (data.avg_volume != null)  items.push(`Avg vol: ${(data.avg_volume / 1e6).toFixed(2)}M`)
  if (data.multiplier != null)  items.push(`${data.multiplier}× avg`)
  if (data.high_52w != null)    items.push(`52W high: ${cur}${data.high_52w}`)
  if (data.low_52w != null)     items.push(`52W low: ${cur}${data.low_52w}`)

  return (
    <div className="flex flex-wrap gap-2 mt-1">
      {items.map((item, i) => (
        <span key={i} className="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded">
          {item}
        </span>
      ))}
    </div>
  )
}

function NewsArticle({ article, index }) {
  const sourceBadge = article.source === 'newsapi'
    ? <span className="text-xs bg-indigo-900 text-indigo-300 px-1.5 py-0.5 rounded font-medium">NewsAPI</span>
    : <span className="text-xs bg-gray-700 text-gray-400 px-1.5 py-0.5 rounded">yfinance</span>

  const date = article.published_at
    ? (() => {
        try {
          const d = new Date(article.published_at)
          return isNaN(d) ? article.published_at : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
        } catch { return article.published_at }
      })()
    : null

  return (
    <div className={`${index > 0 ? 'border-t border-gray-800 pt-2 mt-2' : ''}`}>
      <a
        href={article.link}
        target="_blank"
        rel="noopener noreferrer"
        className="text-sm text-gray-200 hover:text-indigo-300 transition-colors leading-snug block"
      >
        {article.title}
      </a>
      <div className="flex items-center gap-2 mt-0.5">
        {sourceBadge}
        {article.publisher && (
          <span className="text-xs text-gray-500">{article.publisher}</span>
        )}
        {date && <span className="text-xs text-gray-600">{date}</span>}
      </div>
    </div>
  )
}

function AlertCard({ alert }) {
  const [expanded, setExpanded] = useState(true)
  const ts = (() => {
    try {
      const d = new Date(alert.timestamp)
      return isNaN(d) ? alert.timestamp : d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch { return alert.timestamp }
  })()

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <EventBadge type={alert.event_type} />
          <span className="text-sm font-mono font-semibold text-white">{alert.ticker}</span>
          <span className="text-xs text-gray-500 uppercase">{alert.market}</span>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-xs text-gray-600">{ts}</span>
          <span className="text-gray-600 text-xs">{expanded ? '▲' : '▼'}</span>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-800">
          {/* Event details */}
          <div className="pt-3">
            <EventDetail type={alert.event_type} data={alert.event_data} market={alert.market} />
          </div>

          {/* News articles */}
          {alert.news && alert.news.length > 0 ? (
            <div className="mt-3">
              <div className="text-xs text-gray-600 uppercase tracking-wide mb-2">
                Related News ({alert.news.length})
              </div>
              {alert.news.map((article, i) => (
                <NewsArticle key={i} article={article} index={i} />
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-600 mt-3 italic">No news articles found.</p>
          )}
        </div>
      )}
    </div>
  )
}

function AddTickersForm({ onAdd }) {
  const [input, setInput] = useState('')
  const [market, setMarket] = useState('india')
  const markets = ['india', 'us', 'europe', 'japan', 'korea']

  const handleSubmit = (e) => {
    e.preventDefault()
    const tickers = input.split(/[\s,]+/).map(t => t.trim().toUpperCase()).filter(Boolean)
    if (tickers.length) {
      onAdd(tickers, market)
      setInput('')
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="RELIANCE, TCS, INFY …"
          className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
        />
        <select
          value={market}
          onChange={e => setMarket(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-300 focus:outline-none focus:border-indigo-500"
        >
          {markets.map(m => (
            <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>
          ))}
        </select>
      </div>
      <button
        type="submit"
        className="w-full px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded transition-colors"
      >
        Add to watchlist
      </button>
    </form>
  )
}

export default function NewsAlerts() {
  const [alerts, setAlerts] = useState([])
  const [watchlist, setWatchlist] = useState({})
  const [status, setStatus] = useState('connecting')   // connecting | live | error | closed
  const [filterMarket, setFilterMarket] = useState('all')
  const [filterEvent, setFilterEvent] = useState('all')
  const esRef = useRef(null)

  // ── SSE connection ───────────────────────────────────────────────────────────
  useEffect(() => {
    const es = new EventSource(`${BASE_URL}/api/alerts/stream`)
    esRef.current = es

    es.onopen = () => setStatus('live')
    es.onerror = () => setStatus('error')

    es.onmessage = (e) => {
      try {
        const alert = JSON.parse(e.data)
        setAlerts(prev => {
          // deduplicate by id
          if (prev.some(a => a.id === alert.id)) return prev
          return [alert, ...prev].slice(0, 200)
        })
      } catch (_) {}
    }

    return () => {
      es.close()
      setStatus('closed')
    }
  }, [])

  // ── watchlist ops ────────────────────────────────────────────────────────────
  const refreshWatchlist = useCallback(async () => {
    try {
      const r = await fetch(`${BASE_URL}/api/alerts/portfolio`)
      const data = await r.json()
      setWatchlist(data.watched || {})
    } catch (_) {}
  }, [])

  useEffect(() => { refreshWatchlist() }, [refreshWatchlist])

  const handleAdd = useCallback(async (tickers, market) => {
    try {
      await fetch(`${BASE_URL}/api/alerts/portfolio`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers, market }),
      })
      await refreshWatchlist()
    } catch (_) {}
  }, [refreshWatchlist])

  const handleRemove = useCallback(async (ticker) => {
    try {
      await fetch(`${BASE_URL}/api/alerts/portfolio/${ticker}`, { method: 'DELETE' })
      await refreshWatchlist()
    } catch (_) {}
  }, [refreshWatchlist])

  const handleTrigger = useCallback(async (ticker, market) => {
    try {
      await fetch(`${BASE_URL}/api/alerts/trigger/${ticker}?market=${market}`, { method: 'POST' })
    } catch (_) {}
  }, [])

  // ── filtered view ────────────────────────────────────────────────────────────
  const filtered = alerts.filter(a => {
    if (filterMarket !== 'all' && a.market !== filterMarket) return false
    if (filterEvent !== 'all' && a.event_type !== filterEvent) return false
    return true
  })

  const statusDot = {
    connecting: 'bg-yellow-400',
    live: 'bg-green-400',
    error: 'bg-red-400',
    closed: 'bg-gray-500',
  }[status]

  const eventTypes = [...new Set(alerts.map(a => a.event_type))]
  const markets = [...new Set(alerts.map(a => a.market))]

  return (
    <div className="grid grid-cols-12 gap-4">

      {/* ── Left panel: watchlist + controls ─────────────────────────────────── */}
      <div className="col-span-12 lg:col-span-3 space-y-4">

        {/* Connection status */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-1">
            <span className={`w-2 h-2 rounded-full ${statusDot}`} />
            <span className="text-sm font-medium text-gray-200">
              {status === 'live' ? 'Live stream connected' : status === 'connecting' ? 'Connecting…' : status === 'error' ? 'Connection error' : 'Stream closed'}
            </span>
          </div>
          <p className="text-xs text-gray-600">
            {alerts.length} alert{alerts.length !== 1 ? 's' : ''} received
          </p>
        </div>

        {/* Add tickers */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-300">Watch tickers</h3>
          <AddTickersForm onAdd={handleAdd} />
          <p className="text-xs text-gray-600">
            Set <code className="text-gray-500">NEWSAPI_KEY</code> env var for NewsAPI coverage;
            falls back to yfinance news.
          </p>
        </div>

        {/* Watchlist */}
        {Object.keys(watchlist).length > 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
            <h3 className="text-sm font-semibold text-gray-300">
              Watchlist ({Object.keys(watchlist).length})
            </h3>
            {Object.entries(watchlist).map(([ticker, market]) => (
              <div key={ticker} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono text-gray-200">{ticker}</span>
                  <span className="text-xs text-gray-600">{market}</span>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleTrigger(ticker, market)}
                    title="Fetch news now"
                    className="text-xs text-indigo-400 hover:text-indigo-300 px-1.5 py-0.5 rounded hover:bg-indigo-900/30 transition-colors"
                  >
                    fetch
                  </button>
                  <button
                    onClick={() => handleRemove(ticker)}
                    title="Remove"
                    className="text-xs text-gray-600 hover:text-red-400 px-1.5 py-0.5 rounded hover:bg-red-900/30 transition-colors"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Filters */}
        {alerts.length > 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-300">Filter alerts</h3>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Market</label>
              <select
                value={filterMarket}
                onChange={e => setFilterMarket(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-300"
              >
                <option value="all">All markets</option>
                {markets.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Event type</label>
              <select
                value={filterEvent}
                onChange={e => setFilterEvent(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-300"
              >
                <option value="all">All events</option>
                {eventTypes.map(t => (
                  <option key={t} value={t}>{EVENT_META[t]?.label || t}</option>
                ))}
              </select>
            </div>
            {(filterMarket !== 'all' || filterEvent !== 'all') && (
              <button
                onClick={() => { setFilterMarket('all'); setFilterEvent('all') }}
                className="text-xs text-gray-500 hover:text-gray-300"
              >
                Clear filters
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── Right panel: alert feed ───────────────────────────────────────────── */}
      <div className="col-span-12 lg:col-span-9 space-y-3">
        {Object.keys(watchlist).length === 0 && alerts.length === 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-8 text-center space-y-2">
            <div className="text-4xl">📡</div>
            <p className="text-gray-400 font-medium">No tickers watched yet</p>
            <p className="text-sm text-gray-600">
              Add ticker symbols to the watchlist. The monitor polls every 5 minutes
              and fetches news when it detects price moves ≥ 2%, RSI crossings,
              volume surges, or 52-week extremes.
            </p>
            <p className="text-sm text-gray-600 mt-2">
              Click <strong className="text-gray-400">fetch</strong> next to any watchlist ticker
              to immediately pull news without waiting for an event.
            </p>
          </div>
        )}

        {Object.keys(watchlist).length > 0 && filtered.length === 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 text-center space-y-1">
            <div className="text-2xl">⏳</div>
            <p className="text-gray-400 text-sm">Watching {Object.keys(watchlist).length} ticker{Object.keys(watchlist).length !== 1 ? 's' : ''} — waiting for events</p>
            <p className="text-xs text-gray-600">
              First poll runs within 5 minutes. Use the <strong className="text-gray-500">fetch</strong> button to pull news immediately.
            </p>
          </div>
        )}

        {filtered.map(alert => (
          <AlertCard key={alert.id} alert={alert} />
        ))}
      </div>
    </div>
  )
}
