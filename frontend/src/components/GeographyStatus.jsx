import { useEffect, useState } from 'react'
import { fetchGeographyStatus } from '../api'

function CoverageBar({ pct }) {
  const w   = Math.min(100, pct ?? 0)
  const cls = w >= 80 ? 'bg-emerald-500' : w >= 40 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2 min-w-[90px]">
      <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${cls}`} style={{ width: `${w}%` }} />
      </div>
      <span className={`text-xs font-mono tabular-nums w-10 text-right
        ${w >= 80 ? 'text-emerald-400' : w >= 40 ? 'text-amber-400' : 'text-red-400'}`}>
        {w.toFixed(0)}%
      </span>
    </div>
  )
}

function MarketBadge({ market }) {
  const MAP = {
    india:     'bg-orange-900/50 text-orange-300 border-orange-800',
    us:        'bg-blue-900/50 text-blue-300 border-blue-800',
    europe:    'bg-indigo-900/50 text-indigo-300 border-indigo-800',
    japan:     'bg-red-900/50 text-red-300 border-red-800',
    korea:     'bg-cyan-900/50 text-cyan-300 border-cyan-800',
    china:     'bg-yellow-900/50 text-yellow-300 border-yellow-800',
    hong_kong: 'bg-rose-900/50 text-rose-300 border-rose-800',
    canada:    'bg-red-900/50 text-red-200 border-red-700',
  }
  const LABEL = {
    india: 'India', us: 'US', europe: 'Europe', japan: 'Japan',
    korea: 'Korea', china: 'China', hong_kong: 'HK', canada: 'CA',
  }
  const cls = MAP[market] ?? 'bg-gray-800 text-gray-400 border-gray-700'
  return (
    <span className={`inline-flex px-1.5 py-0.5 rounded border text-[10px] font-medium ${cls}`}>
      {LABEL[market] ?? market}
    </span>
  )
}

function SummaryCard({ label, value, sub }) {
  return (
    <div className="bg-gray-800/60 border border-gray-700 rounded-lg px-4 py-3">
      <p className="text-xs text-gray-500 mb-0.5">{label}</p>
      <p className="text-xl font-bold text-gray-100 tabular-nums">{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

export default function GeographyStatus() {
  const [state, setState] = useState({ loading: true, data: null, error: null })
  const [sortKey, setSortKey] = useState('instruments')
  const [sortDir, setSortDir] = useState('desc')
  const [filterMarket, setFilterMarket] = useState('all')

  const load = () => {
    setState(s => ({ ...s, loading: true, error: null }))
    fetchGeographyStatus()
      .then(d => setState({ loading: false, data: d, error: null }))
      .catch(e => setState({ loading: false, data: null, error: e.message }))
  }

  useEffect(() => { load() }, [])

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const rows = state.data?.rows ?? []
  const summary = state.data?.summary ?? {}

  const markets = ['all', ...Array.from(new Set(rows.map(r => r.market)))]

  const filtered = rows.filter(r => filterMarket === 'all' || r.market === filterMarket)

  const sorted = [...filtered].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey]
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    return sortDir === 'asc' ? va - vb : vb - va
  })

  const Th = ({ k, label, cls = '' }) => (
    <th
      onClick={() => toggleSort(k)}
      className={`px-3 py-2.5 text-left text-xs font-medium text-gray-500 cursor-pointer
        hover:text-gray-300 select-none whitespace-nowrap ${cls}`}
    >
      {label}
      {sortKey === k && <span className="ml-1 font-mono">{sortDir === 'asc' ? '↑' : '↓'}</span>}
    </th>
  )

  const MARKET_LABEL = {
    india: 'India', us: 'US', europe: 'Europe', japan: 'Japan',
    korea: 'Korea', china: 'China', hong_kong: 'Hong Kong', canada: 'Canada',
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Market Coverage by Geography</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Instruments seeded · Quotes fetched · Coverage across all exchanges
          </p>
        </div>
        <button
          onClick={load}
          disabled={state.loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700
            disabled:opacity-50 text-xs font-medium text-gray-300 transition-colors"
        >
          {state.loading
            ? <><span className="inline-block w-3 h-3 border border-gray-400/30 border-t-gray-300 rounded-full animate-spin" /> Refreshing…</>
            : '↻ Refresh'}
        </button>
      </div>

      {/* Summary cards */}
      {summary.total_instruments > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 px-5 py-4 border-b border-gray-800/60">
          <SummaryCard
            label="Total Instruments"
            value={summary.total_instruments?.toLocaleString()}
            sub="across all markets"
          />
          <SummaryCard
            label="Quotes Available"
            value={summary.total_quotes?.toLocaleString()}
            sub={`${summary.overall_coverage}% overall coverage`}
          />
          <SummaryCard
            label="Countries / Exchanges"
            value={summary.total_countries}
            sub={`${summary.markets} market groups`}
          />
          <SummaryCard
            label="Overall Coverage"
            value={`${summary.overall_coverage}%`}
            sub="instruments with live quotes"
          />
        </div>
      )}

      {state.error && (
        <div className="mx-5 mt-3 p-3 bg-red-950/50 border border-red-800 rounded-lg text-red-300 text-sm">
          {state.error}
        </div>
      )}

      {state.loading && !state.data && (
        <div className="py-20 text-center">
          <div className="inline-block w-7 h-7 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin mb-3" />
          <p className="text-gray-500 text-sm">Loading geography data…</p>
        </div>
      )}

      {state.data && (
        <>
          {/* Market filter */}
          <div className="flex items-center gap-2 px-5 py-2.5 border-b border-gray-800/60 overflow-x-auto">
            <span className="text-xs text-gray-600 shrink-0">Filter:</span>
            {markets.map(m => (
              <button
                key={m}
                onClick={() => setFilterMarket(m)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${
                  filterMarket === m
                    ? 'bg-indigo-700 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                }`}
              >
                {m === 'all' ? `All (${rows.length})` : MARKET_LABEL[m] ?? m}
              </button>
            ))}
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <Th k="flag"          label=""        cls="w-8" />
                  <Th k="country"       label="Country" />
                  <Th k="market"        label="Market"  />
                  <Th k="exchange"      label="Exchange" />
                  <Th k="instruments"   label="Tickers Seeded" />
                  <Th k="quotes"        label="Quotes Available" />
                  <Th k="coverage_pct"  label="Coverage" />
                </tr>
              </thead>
              <tbody>
                {sorted.map((row, i) => {
                  const isEu = row.market === 'europe'
                  const bg   = i % 2 === 0 ? 'bg-gray-900/30' : ''
                  return (
                    <tr key={`${row.country}-${i}`}
                        className={`border-b border-gray-800/30 hover:bg-gray-800/30 transition-colors ${bg}`}>
                      <td className="px-3 py-2.5 text-lg leading-none">{row.flag}</td>
                      <td className="px-3 py-2.5">
                        <span className="text-gray-100 font-medium text-sm">{row.country}</span>
                        {row.suffix && (
                          <span className="ml-1.5 text-[10px] font-mono text-gray-600">{row.suffix}</span>
                        )}
                        {isEu && (
                          <span className="ml-1.5 text-[10px] text-indigo-600">EU</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        <MarketBadge market={row.market} />
                      </td>
                      <td className="px-3 py-2.5 text-gray-400 text-xs">{row.exchange}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-xs text-gray-300 tabular-nums">
                        {row.instruments.toLocaleString()}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums">
                        <span className={row.quotes > 0 ? 'text-emerald-400' : 'text-gray-600'}>
                          {row.quotes.toLocaleString()}
                        </span>
                        {row.note && (
                          <span className="ml-1 text-[9px] text-gray-700">~est</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 min-w-[130px]">
                        <CoverageBar pct={row.coverage_pct} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>

              {/* Totals footer */}
              <tfoot>
                <tr className="border-t border-gray-700 bg-gray-800/50">
                  <td colSpan={4} className="px-3 py-2.5 text-xs font-semibold text-gray-300">
                    {filterMarket === 'all' ? 'TOTAL' : `${MARKET_LABEL[filterMarket] ?? filterMarket} TOTAL`}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-xs font-bold text-gray-100 tabular-nums">
                    {sorted.reduce((a, r) => a + (r.market === 'europe' && filterMarket === 'all'
                      ? 0   // europe individual rows already counted in summary
                      : r.instruments), 0).toLocaleString()}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-xs font-bold text-emerald-400 tabular-nums">
                    {sorted.reduce((a, r) => a + (r.market === 'europe' && filterMarket === 'all'
                      ? 0 : r.quotes), 0).toLocaleString()}
                  </td>
                  <td className="px-3 py-2.5">
                    {filterMarket === 'all' && summary.overall_coverage != null && (
                      <CoverageBar pct={summary.overall_coverage} />
                    )}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Legend */}
          <div className="px-5 py-3 border-t border-gray-800/60 flex items-center gap-4 text-[10px] text-gray-600">
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-1.5 rounded-full bg-emerald-500 inline-block" /> ≥80% coverage
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-1.5 rounded-full bg-amber-500 inline-block" /> 40–79%
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-1.5 rounded-full bg-red-500 inline-block" /> &lt;40%
            </span>
            <span className="ml-auto">Europe per-exchange quote counts are proportionally estimated</span>
          </div>
        </>
      )}
    </div>
  )
}
