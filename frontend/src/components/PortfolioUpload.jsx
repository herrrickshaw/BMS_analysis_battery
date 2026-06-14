import { useRef, useState } from 'react'
import { parsePortfolio } from '../api'

const ACCEPT = '.xlsx,.xls,.pdf'

const MARKETS = [
  { id: 'india',  label: '🇮🇳 India',  sub: 'NSE / BSE',        suffix: '.NS' },
  { id: 'us',     label: '🇺🇸 USA',     sub: 'NYSE / NASDAQ',    suffix: '' },
  { id: 'europe', label: '🇪🇺 Europe',  sub: 'STOXX 600',        suffix: '.PA / .DE …' },
  { id: 'japan',  label: '🇯🇵 Japan',   sub: 'TSE',              suffix: '.T' },
  { id: 'korea',  label: '🇰🇷 Korea',   sub: 'KRX',              suffix: '.KS' },
  { id: 'china',  label: '🇨🇳 China',   sub: 'SSE / SZSE',       suffix: '.SS / .SZ' },
]

const MATCH_COLOR = {
  'symbol':       'text-emerald-400',
  'ISIN':         'text-blue-400',
  'name (fuzzy)': 'text-amber-400',
}

export default function PortfolioUpload({ onFetchSymbols, loading }) {
  const inputRef = useRef(null)
  const [market,   setMarket]   = useState('india')
  const [parsing,  setParsing]  = useState(false)
  const [stocks,   setStocks]   = useState(null)
  const [warnings, setWarnings] = useState([])
  const [meta,     setMeta]     = useState(null)
  const [error,    setError]    = useState(null)
  const [selected, setSelected] = useState(new Set())
  const [dragging, setDragging] = useState(false)

  const handleFile = async (file) => {
    if (!file) return
    setParsing(true); setError(null); setStocks(null); setSelected(new Set())
    try {
      const result = await parsePortfolio(file, market)
      setStocks(result.stocks)
      setWarnings(result.warnings || [])
      setMeta(result.meta)
      setSelected(new Set(result.stocks.map(s => s.yf_ticker || s.symbol)))
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

  const key = (s) => s.yf_ticker || s.symbol

  const toggleAll = () => {
    if (selected.size === stocks.length) setSelected(new Set())
    else setSelected(new Set(stocks.map(key)))
  }

  const toggle = (k) => setSelected(prev => {
    const next = new Set(prev)
    next.has(k) ? next.delete(k) : next.add(k)
    return next
  })

  const handleFetch = () => {
    const syms = stocks.filter(s => selected.has(key(s))).map(key)
    if (syms.length) onFetchSymbols(syms, market)
  }

  const reset = () => { setStocks(null); setWarnings([]); setMeta(null); setError(null) }

  const activeMkt = MARKETS.find(m => m.id === market)

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Portfolio / Watchlist Upload
        </h3>
        <p className="text-xs text-gray-600 mt-0.5">Excel or PDF — tickers extracted automatically</p>
      </div>

      <div className="p-3 space-y-3">
        {/* Market selector */}
        <div>
          <label className="text-xs text-gray-500 mb-1.5 block">Select market</label>
          <div className="grid grid-cols-3 gap-1">
            {MARKETS.map(m => (
              <button
                key={m.id}
                onClick={() => { setMarket(m.id); reset() }}
                title={`${m.label} — ${m.sub}`}
                className={`flex flex-col items-center py-2 px-1 rounded-lg text-xs transition-colors border ${
                  market === m.id
                    ? 'bg-indigo-700/40 border-indigo-600 text-indigo-200'
                    : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-gray-200 hover:border-gray-600'
                }`}
              >
                <span className="text-base leading-tight">{m.label.split(' ')[0]}</span>
                <span className="text-gray-500 mt-0.5 font-mono" style={{fontSize:'9px'}}>{m.sub}</span>
              </button>
            ))}
          </div>
          {activeMkt && (
            <p className="text-xs text-gray-700 mt-1">
              yfinance symbols: <span className="font-mono text-gray-600">{activeMkt.suffix || 'no suffix (e.g. AAPL)'}</span>
            </p>
          )}
        </div>

        {/* Drop zone */}
        {!stocks && (
          <div
            className={`border-2 border-dashed rounded-lg px-3 py-5 text-center transition-colors cursor-pointer ${
              dragging ? 'border-violet-500 bg-violet-950/20' : 'border-gray-700 hover:border-gray-600'
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
                <p className="text-xl mb-1">📄</p>
                <p className="text-xs text-gray-400 font-medium">Drop file or click to browse</p>
                <p className="text-xs text-gray-600 mt-0.5">.xlsx · .xls · .pdf</p>
              </>
            )}
          </div>
        )}

        {error && (
          <div className="px-3 py-2 bg-red-950/40 border border-red-800 rounded text-xs text-red-300">
            {error}
          </div>
        )}

        {/* Results */}
        {stocks && (
          <>
            {/* Summary row */}
            <div className="flex items-center gap-2 flex-wrap text-xs">
              <span className="text-gray-300 font-medium">{stocks.length} tickers found</span>
              {meta?.db_size && (
                <span className="text-gray-600">· from {meta.db_size.toLocaleString()}-stock DB</span>
              )}
              {meta?.pages_scanned > 0 && (
                <span className="text-gray-600">· {meta.pages_scanned} pages</span>
              )}
              {meta?.sheets_scanned?.length > 0 && (
                <span className="text-gray-600 truncate max-w-[160px]"
                  title={meta.sheets_scanned.join(', ')}>
                  · {meta.sheets_scanned.length} sheet{meta.sheets_scanned.length > 1 ? 's' : ''}
                </span>
              )}
              {meta?.quotes_enriched > 0 && (
                <span className="text-green-600 font-medium">
                  · {meta.quotes_enriched} live quotes cached
                </span>
              )}
              {meta?.cassandra === 'online' && !meta?.quotes_enriched && (
                <span className="text-gray-700">· Cassandra online</span>
              )}
            </div>

            {/* Warnings */}
            {warnings.map((w, i) => (
              <div key={i} className="px-2 py-1.5 bg-amber-950/30 border border-amber-900/50 rounded text-xs text-amber-400 leading-relaxed">
                ⚠ {w}
              </div>
            ))}

            {/* Legend */}
            <div className="flex items-center gap-3 text-xs">
              <span className="text-emerald-400">● symbol</span>
              <span className="text-blue-400">● ISIN</span>
              <span className="text-amber-400">● name match</span>
            </div>

            {/* Stock list */}
            <div className="max-h-52 overflow-y-auto rounded-lg border border-gray-800 bg-gray-950">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-gray-900 border-b border-gray-800">
                  <tr>
                    <th className="px-2 py-1.5">
                      <input type="checkbox"
                        checked={selected.size === stocks.length && stocks.length > 0}
                        onChange={toggleAll} className="accent-violet-500" />
                    </th>
                    <th className="px-2 py-1.5 text-left text-gray-500 font-medium">Ticker</th>
                    <th className="px-2 py-1.5 text-left text-gray-500 font-medium">Name</th>
                    <th className="px-2 py-1.5 text-left text-gray-500 font-medium">Via</th>
                    <th className="px-2 py-1.5 text-right text-gray-500 font-medium">CMP</th>
                    <th className="px-2 py-1.5 text-left text-gray-500 font-medium">Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {stocks.map(s => {
                    const k = key(s)
                    const isSelected = selected.has(k)
                    return (
                      <tr
                        key={k}
                        onClick={() => toggle(k)}
                        className={`border-b border-gray-800/50 cursor-pointer transition-colors ${
                          isSelected ? 'hover:bg-violet-950/10' : 'opacity-40'
                        }`}
                      >
                        <td className="px-2 py-1.5">
                          <input type="checkbox" checked={isSelected}
                            onChange={() => toggle(k)}
                            onClick={e => e.stopPropagation()}
                            className="accent-violet-500" />
                        </td>
                        <td className="px-2 py-1.5 font-mono font-bold text-gray-200 whitespace-nowrap">
                          {k}
                        </td>
                        <td className="px-2 py-1.5 text-gray-400 truncate max-w-[110px]" title={s.name}>
                          {s.name}
                        </td>
                        <td className={`px-2 py-1.5 whitespace-nowrap ${MATCH_COLOR[s.matched_via] || 'text-gray-600'}`}>
                          {s.matched_via?.split(' ')[0] || '?'}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono text-gray-400 text-xs whitespace-nowrap">
                          {s.quote?.cmp != null ? s.quote.cmp.toFixed(2) : '—'}
                        </td>
                        <td className={`px-2 py-1.5 text-xs font-bold whitespace-nowrap ${
                          s.quote?.rsi_signal === 'BUY'  ? 'text-emerald-400' :
                          s.quote?.rsi_signal === 'SELL' ? 'text-red-400' :
                          s.quote?.rsi_signal === 'HOLD' ? 'text-amber-500' :
                          'text-gray-700'
                        }`}>
                          {s.quote?.rsi_signal ?? '—'}
                          {s.quote?.rsi != null && (
                            <span className="font-normal text-gray-600 ml-1">
                              {s.quote.rsi.toFixed(0)}
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
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
              <button onClick={reset}
                className="px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-xs text-gray-400 transition-colors"
                title="Upload a different file">
                ↺
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
