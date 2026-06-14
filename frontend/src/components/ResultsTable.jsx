import { Fragment, useState } from 'react'
import ScoreBadge from './ScoreBadge'

const RSI_SIGNAL_COL = { key: 'rsi_signal', label: 'RSI Signal', cls: '' }

const COLS = {
  darvas: [
    { key: 'name',         label: 'Company',       cls: 'text-gray-100 font-medium' },
    { key: 'ticker',       label: 'Ticker',         cls: 'text-gray-400 font-mono text-xs' },
    { key: 'sector',       label: 'Sector',         cls: 'text-gray-500 text-xs' },
    { key: 'cmp',          label: 'CMP',            cls: 'text-gray-200', fmt: (v) => v != null ? `₹${v}` : '—' },
    { key: 'market_cap',   label: 'Mkt Cap (Cr)',   cls: 'text-gray-400', fmt: (v) => v != null ? `₹${Number(v).toLocaleString()}` : '—' },
    { key: 'pe',           label: 'P/E',            cls: 'text-gray-400 font-mono', fmt: (v) => v != null ? Number(v).toFixed(1) : '—' },
    { key: 'roe',          label: 'ROE %',          cls: 'text-gray-400 font-mono', fmt: (v) => v != null ? `${Number(v).toFixed(1)}%` : '—' },
    { key: 'score',        label: 'Score',          cls: '' },
    { key: 'completeness', label: 'Data',           cls: '' },
    RSI_SIGNAL_COL,
  ],
  piotroski: [
    { key: 'name',         label: 'Company',        cls: 'text-gray-100 font-medium' },
    { key: 'ticker',       label: 'Ticker',         cls: 'text-gray-400 font-mono text-xs' },
    { key: 'sector',       label: 'Sector',         cls: 'text-gray-500 text-xs' },
    { key: 'cmp',          label: 'CMP',            cls: 'text-gray-200', fmt: (v) => v != null ? `₹${v}` : '—' },
    { key: 'market_cap',   label: 'Mkt Cap (Cr)',   cls: 'text-gray-400', fmt: (v) => v != null ? `₹${Number(v).toLocaleString()}` : '—' },
    { key: 'debt_to_equity', label: 'D/E',          cls: 'text-gray-400 font-mono', fmt: (v) => v != null ? Number(v).toFixed(2) : '—' },
    { key: 'score',        label: 'F-Score',        cls: '' },
    { key: 'completeness', label: 'Data',           cls: '' },
    RSI_SIGNAL_COL,
  ],
  coffee_can: [
    { key: 'name',         label: 'Company',        cls: 'text-gray-100 font-medium' },
    { key: 'ticker',       label: 'Ticker',         cls: 'text-gray-400 font-mono text-xs' },
    { key: 'sector',       label: 'Sector',         cls: 'text-gray-500 text-xs' },
    { key: 'cmp',          label: 'CMP',            cls: 'text-gray-200', fmt: (v) => v != null ? `₹${v}` : '—' },
    { key: 'market_cap',   label: 'Mkt Cap (Cr)',   cls: 'text-gray-400', fmt: (v) => v != null ? `₹${Number(v).toLocaleString()}` : '—' },
    { key: 'roe',          label: 'ROE %',          cls: 'text-gray-400 font-mono', fmt: (v) => v != null ? `${Number(v).toFixed(1)}%` : '—' },
    { key: 'moat_score',   label: 'Moat',           cls: 'text-gray-300 font-mono font-bold' },
    { key: 'score',        label: 'Pass',           cls: '' },
    { key: 'completeness', label: 'Data',           cls: '' },
    RSI_SIGNAL_COL,
  ],
}

const RSI_BADGE = {
  BUY:  'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  SELL: 'bg-red-900/50 text-red-300 border border-red-700',
  HOLD: 'bg-gray-800 text-gray-500 border border-gray-700',
}

function RsiSignalBadge({ signal, rsi, ema50 }) {
  const s = signal ?? 'HOLD'
  return (
    <div className="flex flex-col items-start gap-0.5">
      <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${RSI_BADGE[s] ?? RSI_BADGE.HOLD}`}>
        {s}
      </span>
      {rsi != null && (
        <span className="text-xs font-mono text-gray-600">
          RSI {Number(rsi).toFixed(1)}
          {ema50 != null && <> · EMA50 {Number(ema50).toFixed(1)}</>}
        </span>
      )}
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
          <span className="text-xs text-gray-400 truncate" title={key}>
            {key.replace(/_/g, ' ')}
          </span>
        </div>
      ))}
    </div>
  )
}

const SIGNAL_ROW_BG = {
  BUY:   'hover:bg-emerald-950/20',
  WATCH: 'hover:bg-amber-950/20',
  AVOID: 'hover:bg-red-950/10',
}

export default function ResultsTable({ results, scanType, onExport, loading, sourceLabel }) {
  const [sortKey, setSortKey] = useState('score')
  const [sortDir, setSortDir] = useState('desc')
  const [expanded, setExpanded] = useState(null)

  const cols = COLS[scanType] || COLS.darvas

  const sorted = [...results].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey]
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    return sortDir === 'asc' ? va - vb : vb - va
  })

  const toggle = (key) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('desc') }
  }

  const buyCount    = results.filter((r) => r.signal === 'BUY').length
  const watchCount  = results.filter((r) => r.signal === 'WATCH').length
  const rsiBuyCount  = results.filter((r) => r.rsi_signal === 'BUY').length
  const rsiSellCount = results.filter((r) => r.rsi_signal === 'SELL').length

  if (!results.length && !loading) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-20 text-center">
        <p className="text-3xl font-mono text-gray-700 mb-3">[--]</p>
        <p className="text-gray-400 font-medium">No results yet</p>
        <p className="text-gray-600 text-sm mt-1">Upload a CSV and run a scan</p>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="text-sm font-semibold text-gray-200 capitalize">
            {scanType.replace('_', ' ')} Results
          </h3>
          {sourceLabel && (
            <span className="text-xs px-2 py-0.5 bg-violet-900/40 text-violet-400 rounded-full">
              {sourceLabel}
            </span>
          )}
          <span className="text-xs px-2 py-0.5 bg-gray-800 rounded-full text-gray-400">
            {results.length} stocks
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
          {rsiBuyCount > 0 && (
            <span className="text-xs px-2 py-0.5 bg-emerald-900/30 text-emerald-500 rounded-full border border-emerald-900">
              {rsiBuyCount} RSI BUY
            </span>
          )}
          {rsiSellCount > 0 && (
            <span className="text-xs px-2 py-0.5 bg-red-900/30 text-red-400 rounded-full border border-red-900">
              {rsiSellCount} RSI SELL
            </span>
          )}
        </div>
        <button
          onClick={onExport}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-xs text-gray-300 transition-colors"
        >
          <span className="font-mono">↓</span> Export Excel
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              {cols.map((col) => (
                <th
                  key={col.key}
                  onClick={() => toggle(col.key)}
                  className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 cursor-pointer hover:text-gray-300 select-none whitespace-nowrap"
                >
                  {col.label}
                  {sortKey === col.key && (
                    <span className="ml-1 font-mono">{sortDir === 'asc' ? '↑' : '↓'}</span>
                  )}
                </th>
              ))}
              <th className="w-6" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <Fragment key={`${row.ticker ?? row.name}-${i}`}>
                <tr
                  onClick={() => setExpanded(expanded === i ? null : i)}
                  className={`border-b border-gray-800/40 cursor-pointer transition-colors ${
                    SIGNAL_ROW_BG[row.signal] || ''
                  }`}
                >
                  {cols.map((col) => (
                    <td key={col.key} className={`px-3 py-2.5 whitespace-nowrap ${col.cls || ''}`}>
                      {col.key === 'rsi_signal' ? (
                        <RsiSignalBadge
                          signal={row.rsi_signal}
                          rsi={row.rsi}
                          ema50={row.ema_50}
                        />
                      ) : col.key === 'score' ? (
                        <ScoreBadge
                          score={row.score ?? 0}
                          maxScore={row.max_score ?? 9}
                          signal={row.signal}
                          scanType={scanType}
                        />
                      ) : col.key === 'moat_score' ? (
                        <span className="flex items-center gap-1.5">
                          <span className="font-mono text-gray-200 font-bold">{row.moat_score ?? 0}</span>
                          <span className="text-amber-400 text-xs tracking-wide">
                            {'●'.repeat(row.moat_score ?? 0)}{'○'.repeat(Math.max(0, 5 - (row.moat_score ?? 0)))}
                          </span>
                        </span>
                      ) : col.key === 'completeness' ? (
                        <span className={`text-xs font-mono ${
                          row.completeness >= 70 ? 'text-emerald-400' :
                          row.completeness >= 40 ? 'text-amber-400' : 'text-red-400'
                        }`}>
                          {row.completeness ?? 0}%
                        </span>
                      ) : col.fmt ? (
                        <span>{col.fmt(row[col.key])}</span>
                      ) : (
                        <span>{row[col.key] ?? '—'}</span>
                      )}
                    </td>
                  ))}
                  <td className="px-2 py-2.5 text-gray-700 text-xs font-mono">
                    {expanded === i ? '▲' : '▼'}
                  </td>
                </tr>
                {expanded === i && row.criteria && (
                  <tr>
                    <td colSpan={cols.length + 1} className="px-3 pb-3">
                      <CriteriaGrid criteria={row.criteria} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
