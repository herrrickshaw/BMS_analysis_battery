import { Fragment, useState, useEffect, useRef } from 'react'
import { fetchDailyScan, fetchStockNews, fetchSectorNews } from '../api'
import ScoreBadge from './ScoreBadge'

const MARKET_META = {
  india:  { label: 'India',  flag: '🇮🇳', color: 'bg-orange-900/50 text-orange-300 border-orange-800' },
  us:     { label: 'US',     flag: '🇺🇸', color: 'bg-blue-900/50 text-blue-300 border-blue-800' },
  europe: { label: 'Europe', flag: '🇪🇺', color: 'bg-indigo-900/50 text-indigo-300 border-indigo-800' },
  japan:  { label: 'Japan',  flag: '🇯🇵', color: 'bg-red-900/50 text-red-300 border-red-800' },
  korea:  { label: 'Korea',  flag: '🇰🇷', color: 'bg-cyan-900/50 text-cyan-300 border-cyan-800' },
  china:  { label: 'China',  flag: '🇨🇳', color: 'bg-yellow-900/50 text-yellow-300 border-yellow-800' },
}

const SCAN_META = {
  darvas:    { label: 'Darvas / Buffett', sub: 'Momentum + quality overlay' },
  piotroski: { label: 'Piotroski',        sub: '9-point financial strength' },
}

const RSI_BADGE = {
  BUY:  'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  SELL: 'bg-red-900/50 text-red-300 border border-red-700',
  HOLD: 'bg-gray-800 text-gray-500 border border-gray-700',
}

const SIGNAL_BG = {
  BUY:   'hover:bg-emerald-950/20',
  WATCH: 'hover:bg-amber-950/20',
}

const ALL_MARKETS = ['india', 'us', 'europe', 'japan', 'korea']

const SECTOR_COLOR = {
  'Technology':              'bg-blue-900/60 text-blue-300 border-blue-700',
  'Financial Services':      'bg-emerald-900/60 text-emerald-300 border-emerald-700',
  'Healthcare':              'bg-rose-900/60 text-rose-300 border-rose-700',
  'Energy':                  'bg-amber-900/60 text-amber-300 border-amber-700',
  'Consumer Cyclical':       'bg-orange-900/60 text-orange-300 border-orange-700',
  'Consumer Defensive':      'bg-teal-900/60 text-teal-300 border-teal-700',
  'Industrials':             'bg-slate-700/60 text-slate-300 border-slate-600',
  'Basic Materials':         'bg-yellow-900/60 text-yellow-300 border-yellow-700',
  'Communication Services':  'bg-violet-900/60 text-violet-300 border-violet-700',
  'Utilities':               'bg-cyan-900/60 text-cyan-300 border-cyan-700',
  'Real Estate':             'bg-pink-900/60 text-pink-300 border-pink-700',
}

function SectorBadge({ sector }) {
  if (!sector) return null
  const cls = SECTOR_COLOR[sector] ?? 'bg-gray-800 text-gray-400 border-gray-700'
  return (
    <span className={`inline-flex px-1.5 py-0.5 rounded border text-xs font-medium whitespace-nowrap ${cls}`}>
      {sector}
    </span>
  )
}

function MarketBadge({ market }) {
  const m = MARKET_META[market] || { label: market, flag: '', color: 'bg-gray-800 text-gray-400 border-gray-700' }
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium border ${m.color}`}>
      <span>{m.flag}</span>
      <span>{m.label}</span>
    </span>
  )
}

function SignalBadge({ signal }) {
  const cls = signal === 'BUY'
    ? 'bg-emerald-900/60 text-emerald-300 border-emerald-700'
    : 'bg-amber-900/60 text-amber-300 border-amber-700'
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs font-bold border ${cls}`}>{signal}</span>
  )
}

function RetPct({ value }) {
  if (value == null) return <span className="text-gray-700">—</span>
  const n   = Number(value)
  const cls = n >= 0 ? 'text-emerald-400' : 'text-red-400'
  return <span className={`font-mono text-xs ${cls}`}>{n >= 0 ? '+' : ''}{n.toFixed(2)}%</span>
}

// ── time-ago helper ───────────────────────────────────────────────────────────
function timeAgo(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  if (isNaN(d)) return dateStr
  const diff = Math.floor((Date.now() - d) / 1000)
  if (diff < 60)   return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400)return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function NewsItem({ article }) {
  return (
    <a
      href={article.link}
      target="_blank"
      rel="noopener noreferrer"
      className="block group hover:bg-gray-800/60 rounded-md px-2.5 py-2 transition-colors"
    >
      <p className="text-xs text-gray-200 group-hover:text-white leading-snug line-clamp-2">
        {article.title}
      </p>
      <p className="text-[10px] text-gray-600 mt-0.5 flex gap-1.5 items-center">
        {article.publisher && <span className="text-gray-500">{article.publisher}</span>}
        {article.published_at && (
          <span className="text-gray-700">{timeAgo(article.published_at)}</span>
        )}
        <span className="ml-auto text-indigo-700 group-hover:text-indigo-500 text-[9px] font-mono">↗</span>
      </p>
    </a>
  )
}

function StockNews({ ticker, market }) {
  const [state, setState] = useState({ loading: true, articles: [], error: null })
  const fetched = useRef(false)

  useEffect(() => {
    if (fetched.current) return
    fetched.current = true
    fetchStockNews(ticker, market)
      .then(r => setState({ loading: false, articles: r.articles ?? [], error: null }))
      .catch(e => setState({ loading: false, articles: [], error: e.message }))
  }, [ticker, market])

  if (state.loading) {
    return (
      <div className="flex items-center gap-2 py-4 px-2">
        <span className="inline-block w-3.5 h-3.5 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin" />
        <span className="text-xs text-gray-600">Loading news…</span>
      </div>
    )
  }
  if (state.error || !state.articles.length) {
    return <p className="text-xs text-gray-700 px-2 py-3">No recent news found.</p>
  }
  return (
    <div>
      <p className="text-[10px] text-gray-600 uppercase tracking-wider px-2.5 mb-1 font-medium">Recent News</p>
      <div className="space-y-0.5">
        {state.articles.map((a, i) => <NewsItem key={i} article={a} />)}
      </div>
    </div>
  )
}

function SectorNewsDrawer({ sector, market, onClose }) {
  const [state, setState] = useState({ loading: true, articles: [], error: null })

  useEffect(() => {
    setState({ loading: true, articles: [], error: null })
    fetchSectorNews(sector, market)
      .then(r => setState({ loading: false, articles: r.articles ?? [], error: null }))
      .catch(e => setState({ loading: false, articles: [], error: e.message }))
  }, [sector, market])

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div
        className="w-full max-w-sm h-full bg-gray-950 border-l border-gray-800 flex flex-col shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 shrink-0">
          <div>
            <p className="text-sm font-semibold text-gray-100">{sector} News</p>
            <p className="text-[10px] text-gray-600 mt-0.5">
              {market !== 'all' ? `${MARKET_META[market]?.label ?? market} · ` : ''}Google News
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-600 hover:text-gray-300 text-lg leading-none font-bold px-1"
          >
            ×
          </button>
        </div>
        {/* Drawer body */}
        <div className="flex-1 overflow-y-auto py-2 px-1">
          {state.loading && (
            <div className="flex items-center gap-2 py-6 px-4">
              <span className="inline-block w-4 h-4 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin" />
              <span className="text-xs text-gray-600">Fetching sector news…</span>
            </div>
          )}
          {!state.loading && state.error && (
            <p className="text-xs text-red-400 px-4 py-4">{state.error}</p>
          )}
          {!state.loading && !state.error && !state.articles.length && (
            <p className="text-xs text-gray-600 px-4 py-4">No news found for this sector.</p>
          )}
          {!state.loading && state.articles.map((a, i) => (
            <div key={i} className="border-b border-gray-800/40 last:border-0">
              <NewsItem article={a} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function CriteriaGrid({ criteria }) {
  const entries = Object.entries(criteria).filter(([k]) => !k.startsWith('_'))
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5 p-3 bg-gray-950 rounded-lg mt-0.5 border border-gray-800/50">
      {entries.map(([key, val]) => (
        <div key={key} className="flex items-center gap-1.5 min-w-0">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
            val === true ? 'bg-emerald-500' : val === false ? 'bg-red-500' : 'bg-gray-600'
          }`} />
          <span className="text-xs text-gray-400 truncate">{key.replace(/_/g, ' ')}</span>
        </div>
      ))}
    </div>
  )
}

function ScanTable({ rows, scanType, marketFilter, sectorFilter }) {
  const [sortKey, setSortKey]   = useState('score')
  const [sortDir, setSortDir]   = useState('desc')
  const [expanded, setExpanded] = useState(null)

  const visible = rows
    .filter(r => marketFilter === 'all' || r.market === marketFilter)
    .filter(r => sectorFilter === 'all' || r.sector === sectorFilter)

  const sorted = [...visible].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey]
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    return sortDir === 'asc' ? va - vb : vb - va
  })

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const SortTh = ({ k, label, cls = '' }) => (
    <th
      onClick={() => toggleSort(k)}
      className={`px-3 py-2.5 text-left text-xs font-medium text-gray-500 cursor-pointer hover:text-gray-300 select-none whitespace-nowrap ${cls}`}
    >
      {label}
      {sortKey === k && <span className="ml-1 font-mono">{sortDir === 'asc' ? '↑' : '↓'}</span>}
    </th>
  )

  if (!sorted.length) {
    return (
      <div className="py-16 text-center text-gray-600 text-sm">
        No {SCAN_META[scanType]?.label} signals for this selection
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <SortTh k="market_label"   label="Market" />
            <SortTh k="sector"         label="Sector" />
            <SortTh k="name"           label="Company" />
            <SortTh k="ticker"         label="Ticker" />
            <SortTh k="signal"         label="Signal" />
            <SortTh k="cmp"            label="Price" />
            <SortTh k="score"          label={scanType === 'piotroski' ? 'F-Score' : 'Score'} />
            <SortTh k="pe"             label="P/E" />
            <SortTh k="roe"            label="ROE %" />
            <SortTh k="debt_to_equity" label="D/E" />
            <SortTh k="ret_1d"         label="1D %" />
            <SortTh k="ret_1w"         label="1W %" />
            <SortTh k="ret_1m"         label="1M %" />
            <SortTh k="ret_3m"         label="3M %" />
            <SortTh k="ret_6m"         label="6M %" />
            <SortTh k="ret_1y"         label="1Y %" />
            <SortTh k="ema_200"        label="EMA-200" />
            <SortTh k="macd"           label="MACD" />
            <SortTh k="volume_ratio"   label="Vol×" />
            <SortTh k="beta"           label="Beta" />
            <SortTh k="current_ratio"  label="Curr.R" />
            <SortTh k="rsi"            label="RSI" />
            <SortTh k="completeness"   label="Data" />
            <th className="w-6" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <Fragment key={`${row.ticker}-${i}`}>
              <tr
                onClick={() => setExpanded(expanded === i ? null : i)}
                className={`border-b border-gray-800/40 cursor-pointer transition-colors ${SIGNAL_BG[row.signal] || ''}`}
              >
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <MarketBadge market={row.market} />
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <SectorBadge sector={row.sector} />
                </td>
                <td className="px-3 py-2.5 max-w-[180px]">
                  <p className="text-gray-100 font-medium truncate">{row.name || '—'}</p>
                  {row.industry && (
                    <p className="text-xs text-gray-600 truncate mt-0.5">{row.industry}</p>
                  )}
                </td>
                <td className="px-3 py-2.5 text-gray-400 font-mono text-xs whitespace-nowrap">
                  {row.ticker}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <SignalBadge signal={row.signal} />
                </td>
                <td className="px-3 py-2.5 text-gray-200 whitespace-nowrap font-mono text-xs">
                  {row.cmp != null
                    ? `${row.currency}${Number(row.cmp).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                    : '—'}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <ScoreBadge
                    score={row.score ?? 0}
                    maxScore={row.max_score ?? 7}
                    signal={row.signal}
                    scanType={scanType}
                  />
                </td>
                <td className="px-3 py-2.5 text-gray-400 font-mono text-xs whitespace-nowrap">
                  {row.pe != null ? Number(row.pe).toFixed(1) : '—'}
                </td>
                <td className="px-3 py-2.5 text-gray-400 font-mono text-xs whitespace-nowrap">
                  {row.roe != null ? `${Number(row.roe).toFixed(1)}%` : '—'}
                </td>
                <td className="px-3 py-2.5 text-gray-400 font-mono text-xs whitespace-nowrap">
                  {row.debt_to_equity != null ? Number(row.debt_to_equity).toFixed(2) : '—'}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap"><RetPct value={row.ret_1d} /></td>
                <td className="px-3 py-2.5 whitespace-nowrap"><RetPct value={row.ret_1w} /></td>
                <td className="px-3 py-2.5 whitespace-nowrap"><RetPct value={row.ret_1m} /></td>
                <td className="px-3 py-2.5 whitespace-nowrap"><RetPct value={row.ret_3m} /></td>
                <td className="px-3 py-2.5 whitespace-nowrap"><RetPct value={row.ret_6m} /></td>
                <td className="px-3 py-2.5 whitespace-nowrap"><RetPct value={row.ret_1y} /></td>
                <td className="px-3 py-2.5 font-mono text-xs whitespace-nowrap">
                  {row.ema_200 != null ? (
                    <span className={row.cmp != null && row.cmp > row.ema_200 ? 'text-emerald-400' : 'text-red-400'}>
                      {Number(row.ema_200).toLocaleString(undefined, { maximumFractionDigits: 1 })}
                    </span>
                  ) : '—'}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs whitespace-nowrap">
                  {row.macd != null ? (
                    <span className={row.macd_signal != null && row.macd > row.macd_signal ? 'text-emerald-400' : 'text-red-400'}>
                      {Number(row.macd).toFixed(3)}
                    </span>
                  ) : '—'}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs whitespace-nowrap">
                  {row.volume_ratio != null ? (
                    <span className={row.volume_ratio > 1.5 ? 'text-amber-400' : 'text-gray-500'}>
                      {Number(row.volume_ratio).toFixed(1)}×
                    </span>
                  ) : '—'}
                </td>
                <td className="px-3 py-2.5 text-gray-400 font-mono text-xs whitespace-nowrap">
                  {row.beta != null ? Number(row.beta).toFixed(2) : '—'}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs whitespace-nowrap">
                  {row.current_ratio != null ? (
                    <span className={row.current_ratio > 1.5 ? 'text-emerald-400' : 'text-amber-400'}>
                      {Number(row.current_ratio).toFixed(1)}
                    </span>
                  ) : '—'}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <div className="flex flex-col gap-0.5">
                    <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${RSI_BADGE[row.rsi_signal] ?? RSI_BADGE.HOLD}`}>
                      {row.rsi_signal ?? 'HOLD'}
                    </span>
                    {row.rsi != null && (
                      <span className="text-xs font-mono text-gray-600">
                        {Number(row.rsi).toFixed(1)}
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <span className={`text-xs font-mono ${
                    (row.completeness ?? 0) >= 70 ? 'text-emerald-400' :
                    (row.completeness ?? 0) >= 40 ? 'text-amber-400' : 'text-red-400'
                  }`}>
                    {row.completeness ?? 0}%
                  </span>
                </td>
                <td className="px-2 py-2.5 text-gray-700 text-xs font-mono">
                  {expanded === i ? '▲' : '▼'}
                </td>
              </tr>
              {expanded === i && row.criteria && (
                <tr>
                  <td colSpan={24} className="px-3 pb-3">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-0.5">
                      <CriteriaGrid criteria={row.criteria} />
                      <div className="bg-gray-950 rounded-lg border border-gray-800/50 p-1.5">
                        <StockNews ticker={row.ticker} market={row.market} />
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function DailyReport() {
  const [loading,      setLoading]      = useState(false)
  const [error,        setError]        = useState(null)
  const [results,      setResults]      = useState(null)   // { darvas:[...], piotroski:[...] }
  const [totals,       setTotals]       = useState(null)
  const [scanMarkets,  setScanMarkets]  = useState(null)
  const [scannedAt,    setScannedAt]    = useState(null)
  const [activeScan,   setActiveScan]   = useState('darvas')
  const [marketFilter, setMarketFilter] = useState('all')
  const [sectorFilter, setSectorFilter] = useState('all')
  const [sectorNews,   setSectorNews]   = useState(null)  // { sector, market } | null

  const run = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchDailyScan()
      setResults(data.results)
      setTotals(data.totals)
      setScanMarkets(data.markets)
      setScannedAt(new Date().toLocaleTimeString())
      setActiveScan('darvas')
      setMarketFilter('all')
      setSectorFilter('all')
      setSectorNews(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const activeRows = results?.[activeScan] ?? []

  // rows visible after both market + sector filters
  const filteredRows = activeRows
    .filter(r => marketFilter === 'all' || r.market === marketFilter)
    .filter(r => sectorFilter === 'all' || r.sector === sectorFilter)

  const buyCount   = filteredRows.filter(r => r.signal === 'BUY').length
  const watchCount = filteredRows.filter(r => r.signal === 'WATCH').length

  // unique sectors in market-filtered rows, sorted by count desc
  const marketRows   = marketFilter === 'all' ? activeRows : activeRows.filter(r => r.market === marketFilter)
  const sectorCounts = marketRows.reduce((acc, r) => {
    if (r.sector) acc[r.sector] = (acc[r.sector] ?? 0) + 1
    return acc
  }, {})
  const sectors = Object.entries(sectorCounts).sort((a, b) => b[1] - a[1]).map(([s]) => s)
  const hasSectors = sectors.length > 0

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Daily Scan Report</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Darvas/Buffett &amp; Piotroski · All exchanges · BUY &amp; WATCH signals only
            {scannedAt && <span className="ml-2 text-gray-600">· scanned {scannedAt}</span>}
          </p>
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold text-white transition-colors"
        >
          {loading ? (
            <>
              <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Scanning…
            </>
          ) : (
            <>
              <span className="text-base">⚡</span>
              Scan All Markets
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="mx-4 mt-3 p-3 bg-red-950/50 border border-red-800 rounded-lg text-red-300 text-sm flex items-start justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-3 text-red-500 hover:text-red-400 font-bold">×</button>
        </div>
      )}

      {!results && !loading && (
        <div className="py-20 text-center">
          <p className="text-4xl mb-4">📊</p>
          <p className="text-gray-400 font-medium">Run a scan to see results</p>
          <p className="text-gray-600 text-sm mt-1">
            Scans {ALL_MARKETS.length} markets · Cassandra quotes · Darvas/Buffett &amp; Piotroski
          </p>
          <button
            onClick={run}
            disabled={loading}
            className="mt-5 px-6 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-sm font-semibold text-white transition-colors"
          >
            ⚡ Scan All Markets
          </button>
        </div>
      )}

      {loading && (
        <div className="py-20 text-center">
          <div className="inline-block w-8 h-8 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin mb-4" />
          <p className="text-gray-400">Scanning all markets…</p>
          <p className="text-gray-600 text-xs mt-1">Fetching quotes from Cassandra and running scanners</p>
        </div>
      )}

      {sectorNews && (
        <SectorNewsDrawer
          sector={sectorNews.sector}
          market={sectorNews.market}
          onClose={() => setSectorNews(null)}
        />
      )}

      {results && !loading && (
        <>
          {/* Scan type tabs + summary */}
          <div className="flex items-center gap-3 px-4 pt-3 pb-0 border-b border-gray-800 overflow-x-auto">
            {Object.entries(SCAN_META).map(([key, meta]) => {
              const count = totals?.[key] ?? 0
              return (
                <button
                  key={key}
                  onClick={() => { setActiveScan(key); setMarketFilter('all'); setSectorFilter('all') }}
                  className={`flex items-center gap-2 pb-3 px-1 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                    activeScan === key
                      ? 'border-indigo-500 text-indigo-300'
                      : 'border-transparent text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {meta.label}
                  <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                    activeScan === key ? 'bg-indigo-900/60 text-indigo-300' : 'bg-gray-800 text-gray-500'
                  }`}>
                    {count}
                  </span>
                </button>
              )
            })}
          </div>

          {/* Market filter row */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-gray-800/60 overflow-x-auto">
            <span className="text-xs text-gray-600 mr-1 shrink-0">Filter:</span>
            {['all', ...ALL_MARKETS].map(m => {
              const meta  = MARKET_META[m]
              const mRows = m === 'all' ? activeRows : activeRows.filter(r => r.market === m)
              return (
                <button
                  key={m}
                  onClick={() => { setMarketFilter(m); setSectorFilter('all') }}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${
                    marketFilter === m
                      ? 'bg-indigo-700 text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {meta ? `${meta.flag} ${meta.label}` : 'All'}
                  <span className={`ml-0.5 ${marketFilter === m ? 'text-indigo-200' : 'text-gray-600'}`}>
                    ({mRows.length})
                  </span>
                </button>
              )
            })}

            {/* Summary stats */}
            <div className="ml-auto flex items-center gap-2 shrink-0">
              <span className="text-xs px-2 py-0.5 bg-gray-800 rounded-full text-gray-400">
                {filteredRows.length} stocks
              </span>
              {buyCount > 0 && (
                <span className="text-xs px-2 py-0.5 bg-emerald-900/40 text-emerald-400 rounded-full">
                  {buyCount} BUY
                </span>
              )}
              {watchCount > 0 && (
                <span className="text-xs px-2 py-0.5 bg-amber-900/40 text-amber-400 rounded-full">
                  {watchCount} WATCH
                </span>
              )}
            </div>
          </div>

          {/* Sector filter row — shown only when sector data is available */}
          {hasSectors && (
            <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-800/60 overflow-x-auto bg-gray-900/40">
              <span className="text-xs text-gray-600 mr-1 shrink-0">Sector:</span>
              <button
                onClick={() => setSectorFilter('all')}
                className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${
                  sectorFilter === 'all'
                    ? 'bg-indigo-700 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                }`}
              >
                All <span className={sectorFilter === 'all' ? 'text-indigo-200' : 'text-gray-600'}>({marketRows.length})</span>
              </button>
              {sectors.map(s => {
                const cnt    = sectorCounts[s]
                const cls    = SECTOR_COLOR[s] ?? 'bg-gray-800 text-gray-400 border-gray-700'
                const active = sectorFilter === s
                return (
                  <div key={s} className="flex items-center gap-0.5 shrink-0">
                    <button
                      onClick={() => setSectorFilter(s)}
                      className={`flex items-center gap-1 px-2.5 py-1 rounded-l-full text-xs font-medium border border-r-0 transition-colors whitespace-nowrap ${
                        active ? cls + ' opacity-100' : 'bg-gray-800/60 text-gray-400 border-gray-700 hover:text-gray-200'
                      }`}
                    >
                      {s}
                      <span className={active ? 'opacity-70' : 'text-gray-600'}>({cnt})</span>
                    </button>
                    <button
                      title={`${s} news`}
                      onClick={() => setSectorNews(n => n?.sector === s ? null : { sector: s, market: marketFilter })}
                      className="px-1.5 py-1 rounded-r-full bg-gray-800/60 border border-gray-700 hover:bg-gray-700 text-gray-600 hover:text-gray-300 text-[10px] transition-colors"
                    >
                      🗞
                    </button>
                  </div>
                )
              })}
            </div>
          )}

          <ScanTable
            rows={activeRows}
            scanType={activeScan}
            marketFilter={marketFilter}
            sectorFilter={sectorFilter}
          />
        </>
      )}
    </div>
  )
}
