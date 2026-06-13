import { Fragment, useState } from 'react'

const FLAG_BADGE = {
  green: 'bg-emerald-500/20 text-emerald-300 border border-emerald-800',
  amber: 'bg-amber-500/20  text-amber-300  border border-amber-800',
  red:   'bg-red-500/20    text-red-300    border border-red-800',
  na:    'text-gray-600',
}

const FLAG_TEXT = {
  green: 'text-emerald-400',
  amber: 'text-amber-400',
  red:   'text-red-400',
  na:    'text-gray-600',
}

function DeltaPill({ delta_pct, flag }) {
  if (flag === 'na' || delta_pct === null || delta_pct === undefined) {
    return <span className="text-gray-700 text-xs font-mono">—</span>
  }
  const label = delta_pct < 0.1 ? '<0.1%' : `${delta_pct.toFixed(1)}%`
  return (
    <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${FLAG_BADGE[flag]}`}>
      {label}
    </span>
  )
}

function ExpandedDetail({ fields }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 p-3 bg-gray-950 rounded-lg mt-0.5 border border-gray-800/50">
      {fields.map(f => (
        <div key={f.field}>
          <p className="text-xs text-gray-500 mb-1">
            {f.label}
            {f.noisy && <span className="ml-1 text-gray-700" title="Methodology differs between sources">†</span>}
          </p>
          <div className="flex items-center gap-1 font-mono text-xs">
            <span className="text-gray-400">{fmt(f.screener)}</span>
            <span className="text-gray-700">→</span>
            <span className={FLAG_TEXT[f.flag]}>{fmt(f.live)}</span>
          </div>
          {f.delta_pct !== null && f.delta_pct !== undefined && (
            <p className={`text-xs mt-0.5 ${FLAG_TEXT[f.flag]}`}>Δ {f.delta_pct.toFixed(1)}%</p>
          )}
        </div>
      ))}
      <div className="col-span-full text-xs text-gray-700 mt-1">
        † D/E and Promoter/Insider % use different definitions across sources.
      </div>
    </div>
  )
}

function fmt(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return Math.abs(v) > 1000 ? v.toLocaleString() : v.toFixed(2)
  return String(v)
}

export default function ComparisonTable({ data, summary, loading }) {
  const [expanded, setExpanded] = useState(null)
  const [sortKey, setSortKey]   = useState('max_delta')
  const [sortDir, setSortDir]   = useState('desc')

  if (loading) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-16 text-center">
        <p className="text-gray-400 animate-pulse">Comparing…</p>
      </div>
    )
  }

  if (!data?.length) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-16 text-center">
        <p className="text-3xl font-mono text-gray-700 mb-3">[≠]</p>
        <p className="text-gray-400 font-medium">No comparison data</p>
        <p className="text-gray-600 text-sm mt-1">
          Upload a Screener CSV and fetch live data, then click "Compare vs Screener"
        </p>
      </div>
    )
  }

  const toggle = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const sorted = [...data].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey]
    if (typeof va === 'number') return sortDir === 'desc' ? vb - va : va - vb
    if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    return 0
  })

  // Column headers from the first record's fields
  const fieldDefs = data[0]?.fields ?? []

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      {/* Summary bar */}
      {summary && (
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 flex-wrap">
          <span className="text-sm font-semibold text-gray-200">Screener vs Live</span>
          <span className="text-xs text-gray-600">·
            <span className="text-blue-400 ml-1">Screener.in</span>
            <span className="mx-1 text-gray-700">vs</span>
            <span className="text-violet-400">yfinance</span>
            <span className="text-gray-700 ml-1 text-xs" title="D/E and Promoter % use different definitions — see disclaimers">† methodology differs for D/E &amp; Insider %</span>
          </span>
          <span className="text-xs px-2 py-0.5 bg-gray-800 rounded-full text-gray-400">
            {summary.stocks_compared} matched
          </span>
          <span className="text-xs px-2 py-0.5 bg-gray-800 rounded-full text-gray-400">
            avg Δ {summary.avg_delta_pct}%
          </span>
          {summary.high_discrepancy > 0 && (
            <span className="text-xs px-2 py-0.5 bg-red-900/40 text-red-400 rounded-full">
              {summary.high_discrepancy} high (&gt;20%)
            </span>
          )}
          {summary.medium_discrepancy > 0 && (
            <span className="text-xs px-2 py-0.5 bg-amber-900/40 text-amber-400 rounded-full">
              {summary.medium_discrepancy} medium (5–20%)
            </span>
          )}
          {summary.low_discrepancy > 0 && (
            <span className="text-xs px-2 py-0.5 bg-emerald-900/40 text-emerald-400 rounded-full">
              {summary.low_discrepancy} close (&lt;5%)
            </span>
          )}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-800">
              <th
                onClick={() => toggle('name')}
                className="px-3 py-2.5 text-left font-medium text-gray-500 cursor-pointer hover:text-gray-300 whitespace-nowrap"
              >
                Stock {sortKey === 'name' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
              </th>
              {fieldDefs.map(f => (
                <th key={f.field} className="px-2 py-2.5 text-left font-medium text-gray-500 whitespace-nowrap">
                  {f.label} Δ{f.noisy ? '†' : ''}
                </th>
              ))}
              <th
                onClick={() => toggle('max_delta')}
                className="px-2 py-2.5 text-left font-medium text-gray-500 cursor-pointer hover:text-gray-300 whitespace-nowrap"
              >
                Worst {sortKey === 'max_delta' ? (sortDir === 'desc' ? '↓' : '↑') : ''}
              </th>
              <th className="w-6" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((stock, i) => {
              const fMap = Object.fromEntries(stock.fields.map(f => [f.field, f]))
              return (
                <Fragment key={stock.ticker}>
                  <tr
                    onClick={() => setExpanded(expanded === i ? null : i)}
                    className="border-b border-gray-800/40 hover:bg-gray-800/30 cursor-pointer"
                  >
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <div className="text-gray-100 font-medium">{stock.name}</div>
                      <div className="text-gray-500 font-mono">{stock.ticker}</div>
                    </td>
                    {fieldDefs.map(f => (
                      <td key={f.field} className="px-2 py-2.5 whitespace-nowrap">
                        <DeltaPill {...(fMap[f.field] ?? { delta_pct: null, flag: 'na' })} />
                      </td>
                    ))}
                    <td className="px-2 py-2.5 whitespace-nowrap">
                      <span className={`font-mono font-bold px-1.5 py-0.5 rounded ${FLAG_BADGE[stock.overall_flag]}`}>
                        {stock.max_delta}%
                      </span>
                    </td>
                    <td className="px-2 py-2.5 text-gray-700 font-mono">
                      {expanded === i ? '▲' : '▼'}
                    </td>
                  </tr>
                  {expanded === i && (
                    <tr>
                      <td colSpan={fieldDefs.length + 3} className="px-3 pb-3">
                        <ExpandedDetail fields={stock.fields} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
