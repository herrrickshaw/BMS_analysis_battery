import { useRef, useState } from 'react'
import { parsePortfolio } from '../api'

const ACCEPT = '.xlsx,.xls,.pdf'

export default function PortfolioUpload({ market, onFetchSymbols, loading }) {
  const inputRef = useRef(null)
  const [parsing,  setParsing]  = useState(false)
  const [stocks,   setStocks]   = useState(null)   // [{symbol, name, isin, matched_via}]
  const [warnings, setWarnings] = useState([])
  const [meta,     setMeta]     = useState(null)
  const [error,    setError]    = useState(null)
  const [selected, setSelected] = useState(new Set())
  const [dragging, setDragging] = useState(false)

  const handleFile = async (file) => {
    if (!file) return
    setParsing(true); setError(null); setStocks(null); setSelected(new Set())
    try {
      const result = await parsePortfolio(file)
      setStocks(result.stocks)
      setWarnings(result.warnings || [])
      setMeta(result.meta)
      setSelected(new Set(result.stocks.map(s => s.symbol)))
    } catch (e) {
      setError(e.message)
    } finally {
      setParsing(false)
    }
  }

  const onDrop = (e) => {
    e.preventDefault(); setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  const toggleAll = () => {
    if (selected.size === stocks.length) setSelected(new Set())
    else setSelected(new Set(stocks.map(s => s.symbol)))
  }

  const toggle = (sym) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(sym) ? next.delete(sym) : next.add(sym)
      return next
    })
  }

  const handleFetch = () => {
    const syms = stocks.filter(s => selected.has(s.symbol)).map(s => s.symbol)
    if (syms.length) onFetchSymbols(syms)
  }

  const matchColor = (via) => {
    if (!via) return 'text-gray-600'
    if (via === 'symbol') return 'text-emerald-400'
    if (via === 'ISIN')   return 'text-blue-400'
    return 'text-amber-400'
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Portfolio / Watchlist Upload
        </h3>
        <p className="text-xs text-gray-600 mt-0.5">Excel or PDF — tickers extracted automatically</p>
      </div>

      {/* Drop zone */}
      {!stocks && (
        <div
          className={`m-3 border-2 border-dashed rounded-lg px-4 py-6 text-center transition-colors cursor-pointer ${
            dragging
              ? 'border-violet-500 bg-violet-950/20'
              : 'border-gray-700 hover:border-gray-600'
          }`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
        >
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={e => handleFile(e.target.files[0])}
          />
          {parsing ? (
            <p className="text-xs text-violet-400 animate-pulse">Extracting tickers…</p>
          ) : (
            <>
              <p className="text-2xl mb-1">📄</p>
              <p className="text-xs text-gray-400 font-medium">Drop Excel or PDF here</p>
              <p className="text-xs text-gray-600 mt-0.5">.xlsx · .xls · .pdf</p>
              <p className="text-xs text-gray-700 mt-2">
                Brokerage statements, portfolio trackers, watchlists
              </p>
            </>
          )}
        </div>
      )}

      {error && (
        <div className="mx-3 mb-3 px-3 py-2 bg-red-950/40 border border-red-800 rounded text-xs text-red-300">
          {error}
        </div>
      )}

      {/* Extracted stocks */}
      {stocks && (
        <div className="p-3 space-y-2">
          {/* Summary */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-400 font-medium">
              {stocks.length} tickers extracted
            </span>
            {meta?.pages_scanned > 0 && (
              <span className="text-xs text-gray-600">· {meta.pages_scanned} pages</span>
            )}
            {meta?.sheets_scanned?.length > 0 && (
              <span className="text-xs text-gray-600">· sheets: {meta.sheets_scanned.join(', ')}</span>
            )}
          </div>

          {/* Warnings */}
          {warnings.map((w, i) => (
            <div key={i} className="px-2 py-1.5 bg-amber-950/30 border border-amber-900/50 rounded text-xs text-amber-400 leading-relaxed">
              ⚠ {w}
            </div>
          ))}

          {/* Match legend */}
          <div className="flex items-center gap-3 text-xs">
            <span className="text-emerald-400">● symbol</span>
            <span className="text-blue-400">● ISIN</span>
            <span className="text-amber-400">● name match</span>
          </div>

          {/* Stock list */}
          <div className="max-h-56 overflow-y-auto rounded-lg border border-gray-800 bg-gray-950">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-gray-900 border-b border-gray-800">
                <tr>
                  <th className="px-2 py-2 text-left">
                    <input
                      type="checkbox"
                      checked={selected.size === stocks.length}
                      onChange={toggleAll}
                      className="accent-violet-500"
                    />
                  </th>
                  <th className="px-2 py-2 text-left text-gray-500 font-medium">Ticker</th>
                  <th className="px-2 py-2 text-left text-gray-500 font-medium">Company</th>
                  <th className="px-2 py-2 text-left text-gray-500 font-medium">Via</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map(s => (
                  <tr
                    key={s.symbol}
                    onClick={() => toggle(s.symbol)}
                    className={`border-b border-gray-800/50 cursor-pointer transition-colors ${
                      selected.has(s.symbol) ? 'bg-violet-950/10' : 'opacity-40'
                    }`}
                  >
                    <td className="px-2 py-1.5">
                      <input
                        type="checkbox"
                        checked={selected.has(s.symbol)}
                        onChange={() => toggle(s.symbol)}
                        onClick={e => e.stopPropagation()}
                        className="accent-violet-500"
                      />
                    </td>
                    <td className="px-2 py-1.5 font-mono font-bold text-gray-200">{s.symbol}</td>
                    <td className="px-2 py-1.5 text-gray-400 truncate max-w-[120px]" title={s.name}>
                      {s.name}
                    </td>
                    <td className={`px-2 py-1.5 ${matchColor(s.matched_via)}`}>
                      {s.matched_via?.split(' ')[0] || '?'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            <button
              onClick={handleFetch}
              disabled={selected.size === 0 || loading}
              className="flex-1 py-2 rounded-lg bg-violet-700 hover:bg-violet-600 disabled:opacity-30 disabled:cursor-not-allowed text-xs font-semibold text-white transition-colors"
            >
              {loading ? 'Fetching…' : `Fetch Live Data (${selected.size})`}
            </button>
            <button
              onClick={() => { setStocks(null); setWarnings([]); setMeta(null) }}
              className="px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-xs text-gray-400 transition-colors"
              title="Upload a different file"
            >
              ↺
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
