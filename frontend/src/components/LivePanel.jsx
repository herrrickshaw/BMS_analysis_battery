import { useState } from 'react'

const NSE_INDICES = [
  { id: '',            label: 'Use uploaded stocks' },
  { id: 'nifty50',    label: 'NIFTY 50  (50 stocks, ~30s)' },
  { id: 'nifty100',   label: 'NIFTY 100  (~1 min)' },
  { id: 'nifty200',   label: 'NIFTY 200  (~2 min)' },
  { id: 'niftymidcap','label': 'NIFTY Midcap 150  (~2 min)' },
  { id: 'nifty500',   label: 'NIFTY 500  (~5 min)' },
]

const STATUS_STYLE = {
  idle:      '',
  resolving: 'text-indigo-400 animate-pulse',
  fetching:  'text-indigo-400 animate-pulse',
  done:      'text-emerald-400',
  error:     'text-red-400',
}

export default function LivePanel({
  market,
  hasScreenerData,
  hasLiveData,
  fetchStatus,
  viewMode,
  onFetch,
  onCompare,
  onScanLive,
}) {
  const isNseMarket = market.startsWith('nse')
  const isFetching  = fetchStatus?.status === 'fetching' || fetchStatus?.status === 'resolving'

  const statusMsg = {
    idle:      '',
    resolving: 'Resolving index symbols…',
    fetching:  `Fetching ${fetchStatus?.total ?? '?'} stocks from Yahoo Finance…`,
    done:      `Done — ${fetchStatus?.done ?? 0} stocks loaded${fetchStatus?.errors ? `, ${fetchStatus.errors} failed` : ''}`,
    error:     `Error: ${fetchStatus?.error ?? 'unknown'}`,
  }[fetchStatus?.status ?? 'idle']

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Live Data
        </h3>
        <span className="text-xs text-gray-600">yfinance</span>
      </div>

      <FetchForm
        isNseMarket={isNseMarket}
        isFetching={isFetching}
        hasScreenerData={hasScreenerData}
        onFetch={onFetch}
      />

      {statusMsg && (
        <p className={`text-xs mt-2 text-center ${STATUS_STYLE[fetchStatus?.status ?? 'idle']}`}>
          {statusMsg}
        </p>
      )}

      {hasLiveData && (
        <div className="mt-3 space-y-1.5">
          <button
            onClick={onScanLive}
            disabled={isFetching}
            className={`w-full py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              viewMode === 'live_scan'
                ? 'bg-violet-700 text-white'
                : 'bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700'
            }`}
          >
            Scan Live Data
          </button>

          {hasScreenerData && (
            <button
              onClick={onCompare}
              disabled={isFetching}
              className={`w-full py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                viewMode === 'compare'
                  ? 'bg-teal-700 text-white'
                  : 'bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700'
              }`}
            >
              Compare vs Screener
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function FetchForm({ isNseMarket, isFetching, hasScreenerData, onFetch }) {
  const [index, setIndex] = useState('')

  const canFetch = index !== '' || hasScreenerData

  return (
    <div className="space-y-2">
      {isNseMarket && (
        <select
          value={index}
          onChange={e => setIndex(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-indigo-500"
        >
          {NSE_INDICES.map(opt => (
            <option key={opt.id} value={opt.id}>{opt.label}</option>
          ))}
        </select>
      )}

      <button
        onClick={() => onFetch(index || null)}
        disabled={isFetching || !canFetch}
        className="w-full py-2 rounded-lg bg-violet-700 hover:bg-violet-600 disabled:opacity-30 disabled:cursor-not-allowed text-sm font-semibold text-white transition-colors"
      >
        {isFetching ? 'Fetching…' : 'Fetch Live Data'}
      </button>

      {!canFetch && (
        <p className="text-xs text-gray-600 text-center">
          Upload a CSV or select an index
        </p>
      )}
    </div>
  )
}
