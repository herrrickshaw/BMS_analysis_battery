import { useEffect, useState } from 'react'
import { fetchSectors } from '../api'

const REGIONS = [
  { id: 'india',  label: 'India' },
  { id: 'us',     label: 'US' },
  { id: 'europe', label: 'Europe' },
]

const COLS = [
  { key: 'industry',          label: 'Industry',       cls: 'text-gray-100 font-medium min-w-[180px]' },
  { key: 'num_firms',         label: 'Firms',          cls: 'text-gray-500 font-mono text-xs' },
  { key: 'trailing_pe',       label: 'Trail P/E',      cls: 'text-gray-300 font-mono' },
  { key: 'forward_pe',        label: 'Fwd P/E',        cls: 'text-gray-400 font-mono' },
  { key: 'peg',               label: 'PEG',            cls: 'text-gray-400 font-mono' },
  { key: 'roe_pct',           label: 'ROE %',          cls: 'text-emerald-400 font-mono' },
  { key: 'opm_pct',           label: 'OPM %',          cls: 'text-indigo-400 font-mono' },
  { key: 'net_margin_pct',    label: 'Net Mgn %',      cls: 'text-indigo-300 font-mono' },
  { key: 'market_de',         label: 'D/E',            cls: 'text-amber-400 font-mono' },
  { key: 'rev_cagr_5y_pct',   label: 'Rev CAGR 5Y',   cls: 'text-cyan-400 font-mono' },
  { key: 'ni_cagr_5y_pct',    label: 'NI CAGR 5Y',    cls: 'text-cyan-300 font-mono' },
]

function fmt(v) {
  if (v === null || v === undefined) return <span className="text-gray-700">—</span>
  if (typeof v === 'number') return v.toFixed(1)
  return v
}

export default function SectorBenchmarks() {
  const [region, setRegion]   = useState('india')
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [filter, setFilter]   = useState('')
  const [sortKey, setSortKey] = useState('trailing_pe')
  const [sortDir, setSortDir] = useState('asc')

  useEffect(() => {
    setLoading(true)
    fetchSectors(region)
      .then(d => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [region])

  const toggle = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const rows = data?.sectors ?? []
  const filtered = rows.filter(r =>
    !filter || r.industry?.toLowerCase().includes(filter.toLowerCase())
  )
  const sorted = [...filtered].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey]
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    return sortDir === 'asc' ? va - vb : vb - va
  })

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 flex-wrap">
        <h3 className="text-sm font-semibold text-gray-200">Sector Benchmarks</h3>
        <span className="text-xs text-gray-600">· Damodaran / NYU Stern</span>

        {/* Region tabs */}
        <div className="flex gap-1 ml-2">
          {REGIONS.map(r => (
            <button
              key={r.id}
              onClick={() => setRegion(r.id)}
              className={`px-2.5 py-0.5 rounded text-xs font-medium transition-colors ${
                region === r.id
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>

        {/* Filter */}
        <input
          type="text"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Filter industry…"
          className="ml-auto bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:outline-none focus:border-indigo-500 w-44"
        />

        <span className="text-xs text-gray-600">{sorted.length} industries</span>
      </div>

      {loading ? (
        <div className="p-16 text-center">
          <p className="text-gray-400 animate-pulse text-sm">Loading Damodaran data…</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-800">
                {COLS.map(col => (
                  <th
                    key={col.key}
                    onClick={() => toggle(col.key)}
                    className="px-3 py-2 text-left font-medium text-gray-500 cursor-pointer hover:text-gray-300 whitespace-nowrap select-none"
                  >
                    {col.label}
                    {sortKey === col.key && (
                      <span className="ml-1 font-mono">{sortDir === 'asc' ? '↑' : '↓'}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => (
                <tr key={i} className="border-b border-gray-800/40 hover:bg-gray-800/30">
                  {COLS.map(col => (
                    <td key={col.key} className={`px-3 py-2 whitespace-nowrap ${col.cls}`}>
                      {fmt(row[col.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="px-4 py-2 border-t border-gray-800 text-xs text-gray-600 flex items-center gap-2 flex-wrap">
        <span className="w-2 h-2 rounded-full bg-amber-400 flex-shrink-0" />
        <span>
          Source: <a href="https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html" target="_blank" rel="noreferrer" className="text-amber-500 hover:text-amber-400 underline underline-offset-2">Aswath Damodaran, NYU Stern</a>
          &nbsp;— sector aggregates updated January 2025. These are industry-level benchmarks, not individual stock data.
          Margins and ROE are displayed as %. Damodaran sector PE is used in the Darvas scan's C9 criterion.
        </span>
      </div>
    </div>
  )
}
