import { useRef, useState } from 'react'
import { parsePortfolio, fetchPortfolioHistory } from '../api'

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
  const [selected,  setSelected]  = useState(new Set())
  const [dragging,  setDragging]  = useState(false)
  const [pnlData,   setPnlData]   = useState(null)
  const [pnlLoading,setPnlLoading]= useState(false)
  const [pnlError,  setPnlError]  = useState(null)

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

  const reset = () => {
    setStocks(null); setWarnings([]); setMeta(null); setError(null)
    setPnlData(null); setPnlError(null)
  }

  const hasPurchaseDates = stocks?.some(s => s.purchase_date)

  const handlePnl = async () => {
    const holdings = stocks
      .filter(s => selected.has(key(s)) && s.purchase_date)
      .map(s => ({
        yf_ticker:      key(s),
        name:           s.name,
        purchase_date:  s.purchase_date,
        purchase_price: s.purchase_price ?? null,
        quantity:       s.quantity ?? null,
      }))
    if (!holdings.length) {
      setPnlError('No selected stocks have a purchase date. Add a "Purchase Date" column to your file.')
      return
    }
    setPnlLoading(true); setPnlError(null); setPnlData(null)
    try {
      const result = await fetchPortfolioHistory(market, holdings)
      setPnlData(result)
    } catch (e) {
      setPnlError(e.message)
    } finally {
      setPnlLoading(false)
    }
  }

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
              {hasPurchaseDates && (
                <button
                  onClick={handlePnl}
                  disabled={pnlLoading || selected.size === 0}
                  className="flex-1 py-2 rounded-lg bg-teal-700 hover:bg-teal-600 disabled:opacity-30 disabled:cursor-not-allowed text-xs font-semibold text-white transition-colors"
                >
                  {pnlLoading ? 'Calculating…' : 'Calculate P&L'}
                </button>
              )}
              <button onClick={reset}
                className="px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-xs text-gray-400 transition-colors"
                title="Upload a different file">
                ↺
              </button>
            </div>

            {/* P&L error */}
            {pnlError && (
              <div className="px-3 py-2 bg-red-950/40 border border-red-800 rounded text-xs text-red-300">
                {pnlError}
              </div>
            )}

            {/* P&L results panel */}
            {pnlData && <PnlPanel data={pnlData} />}
          </>
        )}
      </div>
    </div>
  )
}

// ── P&L Results Panel ─────────────────────────────────────────────────────────

const SIGNAL_CLS = {
  BUY:  'text-emerald-400',
  SELL: 'text-red-400',
  HOLD: 'text-amber-500',
}

function fmt(v, decimals = 0) {
  if (v == null) return '—'
  return v.toLocaleString(undefined, { maximumFractionDigits: decimals, minimumFractionDigits: decimals })
}

function SummaryCard({ label, value, positive, sub }) {
  const cls = positive == null ? 'text-gray-200' : positive ? 'text-emerald-400' : 'text-red-400'
  return (
    <div className="bg-gray-950 border border-gray-800 rounded-lg px-3 py-2">
      <p className="text-gray-600 mb-0.5 text-xs">{label}</p>
      <p className={`font-mono font-bold text-sm ${cls}`}>{value}</p>
      {sub && <p className="text-gray-700 text-xs mt-0.5">{sub}</p>}
    </div>
  )
}

function PnlPanel({ data }) {
  const { holdings, summary } = data
  const totalPnl    = summary?.total_unrealised_pnl
  const totalReturn = summary?.total_return_pnl
  const pnlPos      = totalPnl    != null && totalPnl    >= 0
  const retPos      = totalReturn != null && totalReturn >= 0
  const hasDivs     = (summary?.total_dividends_received ?? 0) > 0

  const sign = (v) => v != null && v >= 0 ? '+' : ''

  return (
    <div className="mt-1 space-y-2">
      {/* Summary grid */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <SummaryCard
          label="Invested"
          value={fmt(summary?.total_cost_basis)}
        />
        <SummaryCard
          label="Current Value"
          value={fmt(summary?.total_current_value)}
        />
        <SummaryCard
          label="Dividends Received"
          value={hasDivs ? `+${fmt(summary.total_dividends_received)}` : '—'}
          positive={hasDivs ? true : null}
        />
        <SummaryCard
          label="Capital P&L"
          value={totalPnl != null ? `${sign(totalPnl)}${fmt(totalPnl)}` : '—'}
          positive={totalPnl != null ? pnlPos : null}
          sub={summary?.total_pnl_pct != null ? `${sign(summary.total_pnl_pct)}${summary.total_pnl_pct.toFixed(2)}%` : null}
        />
        <SummaryCard
          label="Total Return (incl. Div)"
          value={totalReturn != null ? `${sign(totalReturn)}${fmt(totalReturn)}` : '—'}
          positive={totalReturn != null ? retPos : null}
          sub={summary?.total_return_pct != null ? `${sign(summary.total_return_pct)}${summary.total_return_pct.toFixed(2)}%` : null}
        />
        <div className="bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 flex flex-col justify-center">
          <p className="text-gray-600 mb-1 text-xs">RSI Signals</p>
          <div className="flex flex-col gap-0.5">
            {summary?.rsi_buy  > 0 && <span className="text-emerald-400 font-mono text-xs">{summary.rsi_buy} BUY</span>}
            {summary?.rsi_sell > 0 && <span className="text-red-400 font-mono text-xs">{summary.rsi_sell} SELL</span>}
            {summary?.rsi_hold > 0 && <span className="text-gray-500 font-mono text-xs">{summary.rsi_hold} HOLD</span>}
            {!summary?.rsi_buy && !summary?.rsi_sell && !summary?.rsi_hold && <span className="text-gray-700 text-xs">—</span>}
          </div>
        </div>
      </div>

      {/* Per-holding table */}
      <div className="overflow-x-auto rounded-lg border border-gray-800 bg-gray-950">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-900 border-b border-gray-800">
            <tr>
              {[
                'Ticker', 'Buy Date', 'Price@Date', 'Buy Price', 'Current',
                'Qty', 'Dividends', 'Capital P&L', 'Total Rtn', 'Signal'
              ].map(h => (
                <th key={h} className="px-2 py-1.5 text-left text-gray-500 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {holdings.map((h, i) => {
              const capPos = h.unrealised_pnl  != null && h.unrealised_pnl  >= 0
              const retPos = h.total_return_pnl != null && h.total_return_pnl >= 0
              const hasDivRow = h.dividends_received > 0
              return (
                <tr key={`${h.yf_ticker}-${i}`} className="border-b border-gray-800/40">
                  <td className="px-2 py-1.5 font-mono font-bold text-gray-200 whitespace-nowrap">{h.yf_ticker}</td>
                  <td className="px-2 py-1.5 text-gray-500 whitespace-nowrap">{h.purchase_date || '—'}</td>
                  <td className="px-2 py-1.5 font-mono text-gray-400 text-right whitespace-nowrap">
                    {h.price_on_date != null ? h.price_on_date.toFixed(2) : '—'}
                    {h.actual_date && h.actual_date !== h.purchase_date && (
                      <span className="text-gray-700 ml-1">({h.actual_date})</span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 font-mono text-gray-400 text-right whitespace-nowrap">
                    {h.purchase_price != null ? h.purchase_price.toFixed(2) : '—'}
                  </td>
                  <td className="px-2 py-1.5 font-mono text-gray-300 text-right whitespace-nowrap">
                    {h.current_price != null ? h.current_price.toFixed(2) : '—'}
                  </td>
                  <td className="px-2 py-1.5 font-mono text-gray-500 text-right">{h.quantity ?? '—'}</td>

                  {/* Dividends */}
                  <td className="px-2 py-1.5 text-right whitespace-nowrap">
                    {hasDivRow ? (
                      <span className="text-blue-400 font-mono">
                        +{fmt(h.dividends_received)}
                        <span className="text-gray-700 ml-1 font-normal">
                          ({h.dividend_count}×{h.dividends_per_share?.toFixed(2)})
                        </span>
                      </span>
                    ) : <span className="text-gray-700">—</span>}
                  </td>

                  {/* Capital P&L */}
                  <td className={`px-2 py-1.5 font-mono text-right whitespace-nowrap ${h.unrealised_pnl != null ? (capPos ? 'text-emerald-400' : 'text-red-400') : 'text-gray-700'}`}>
                    {h.unrealised_pnl != null
                      ? `${capPos ? '+' : ''}${fmt(h.unrealised_pnl)}`
                      : '—'}
                    {h.pnl_pct != null && (
                      <span className="text-xs font-normal opacity-60 ml-1">
                        {capPos ? '+' : ''}{h.pnl_pct.toFixed(1)}%
                      </span>
                    )}
                  </td>

                  {/* Total return (capital + dividends) */}
                  <td className={`px-2 py-1.5 font-mono text-right whitespace-nowrap font-semibold ${h.total_return_pnl != null ? (retPos ? 'text-emerald-300' : 'text-red-300') : 'text-gray-700'}`}>
                    {h.total_return_pnl != null
                      ? `${retPos ? '+' : ''}${fmt(h.total_return_pnl)}`
                      : '—'}
                    {h.total_return_pct != null && (
                      <span className="text-xs font-normal opacity-70 ml-1">
                        {retPos ? '+' : ''}{h.total_return_pct.toFixed(1)}%
                      </span>
                    )}
                  </td>

                  <td className={`px-2 py-1.5 font-bold whitespace-nowrap ${SIGNAL_CLS[h.rsi_signal] || 'text-gray-700'}`}>
                    {h.rsi_signal ?? '—'}
                    {h.rsi != null && <span className="font-normal text-gray-600 ml-1">{h.rsi.toFixed(0)}</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Dividend payouts detail */}
      {holdings.some(h => h.dividend_payouts?.length > 0) && (
        <details className="text-xs">
          <summary className="text-gray-600 cursor-pointer hover:text-gray-400 select-none py-1">
            Dividend payout history ▸
          </summary>
          <div className="mt-1 space-y-1">
            {holdings.filter(h => h.dividend_payouts?.length > 0).map(h => (
              <div key={h.yf_ticker} className="bg-gray-950 border border-gray-800 rounded-lg px-3 py-2">
                <p className="font-mono font-bold text-gray-300 mb-1">{h.yf_ticker}
                  <span className="font-normal text-gray-600 ml-2">
                    {h.dividend_count} payment{h.dividend_count !== 1 ? 's' : ''} · ₹{h.dividends_per_share?.toFixed(2)}/share · ₹{fmt(h.dividends_received)} total
                  </span>
                </p>
                <div className="flex flex-wrap gap-1">
                  {h.dividend_payouts.map(p => (
                    <span key={p.date} className="px-1.5 py-0.5 bg-blue-950/40 border border-blue-900/40 text-blue-400 rounded font-mono">
                      {p.date} · {p.amount.toFixed(2)}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
