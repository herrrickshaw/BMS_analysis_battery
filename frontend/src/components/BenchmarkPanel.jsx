import { useCallback, useState } from 'react'

const BASE_URL = 'http://localhost:8000'

const BENCHMARKS = [
  { id: 'sp500',  label: 'S&P 500' },
  { id: 'nasdaq', label: 'NASDAQ 100' },
]

const SENTIMENT_COLOR = {
  bullish: 'text-green-400',
  bearish: 'text-red-400',
  neutral: 'text-gray-400',
}

const SENTIMENT_BG = {
  bullish: 'bg-green-900/40 border-green-700',
  bearish: 'bg-red-900/40 border-red-700',
  neutral: 'bg-gray-800 border-gray-700',
}

function MetricCard({ label, value, sub, highlight, positive }) {
  const colour = highlight
    ? positive == null
      ? 'text-white'
      : positive
        ? 'text-green-400'
        : 'text-red-400'
    : 'text-gray-200'
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-lg font-semibold font-mono ${colour}`}>{value ?? '—'}</div>
      {sub && <div className="text-xs text-gray-600 mt-0.5">{sub}</div>}
    </div>
  )
}

function pct(v, decimals = 1) {
  if (v == null) return null
  const sign = v >= 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(decimals)}%`
}

function fmt(v, decimals = 3) {
  if (v == null) return null
  return v.toFixed(decimals)
}

function MetricsGrid({ metrics, benchmark }) {
  const benchLabel = BENCHMARKS.find(b => b.id === benchmark)?.label || benchmark

  return (
    <div className="space-y-4">
      {/* Returns */}
      <div>
        <h4 className="text-xs text-gray-500 uppercase tracking-wide mb-2">Returns</h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard
            label="Portfolio total return"
            value={pct(metrics.portfolio_total_return)}
            highlight positive={metrics.portfolio_total_return >= 0}
          />
          <MetricCard
            label={`${benchLabel} total return`}
            value={pct(metrics.benchmark_total_return)}
            highlight positive={metrics.benchmark_total_return >= 0}
          />
          <MetricCard
            label="Portfolio annualised"
            value={pct(metrics.portfolio_annualised_return)}
            highlight positive={metrics.portfolio_annualised_return >= 0}
          />
          <MetricCard
            label={`${benchLabel} annualised`}
            value={pct(metrics.benchmark_annualised_return)}
            highlight positive={metrics.benchmark_annualised_return >= 0}
          />
        </div>
      </div>

      {/* Risk metrics */}
      <div>
        <h4 className="text-xs text-gray-500 uppercase tracking-wide mb-2">Risk &amp; Attribution</h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard
            label="Alpha (annualised)"
            value={pct(metrics.alpha, 2)}
            sub="Jensen's α vs benchmark"
            highlight
            positive={metrics.alpha >= 0}
          />
          <MetricCard
            label="Beta"
            value={fmt(metrics.beta, 2)}
            sub="Market sensitivity"
          />
          <MetricCard
            label="Sharpe ratio"
            value={fmt(metrics.sharpe_ratio, 2)}
            sub="Annualised, rf=5%"
            highlight
            positive={metrics.sharpe_ratio >= 1}
          />
          <MetricCard
            label="Max drawdown"
            value={pct(metrics.max_drawdown)}
            highlight
            positive={metrics.max_drawdown > -0.1}
          />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
          <MetricCard
            label="Correlation"
            value={fmt(metrics.correlation, 3)}
            sub={`vs ${benchLabel}`}
          />
          <MetricCard
            label="Tracking error"
            value={pct(metrics.tracking_error, 2)}
            sub="Annualised std of excess returns"
          />
          <MetricCard
            label="Information ratio"
            value={fmt(metrics.information_ratio, 2)}
            sub="Active return / tracking error"
            highlight
            positive={metrics.information_ratio >= 0}
          />
        </div>
      </div>

      {/* Volatility */}
      <div>
        <h4 className="text-xs text-gray-500 uppercase tracking-wide mb-2">Volatility</h4>
        <div className="grid grid-cols-2 gap-3">
          <MetricCard label="Portfolio volatility (ann.)" value={pct(metrics.portfolio_volatility)} />
          <MetricCard label={`${benchLabel} volatility (ann.)`} value={pct(metrics.benchmark_volatility)} />
        </div>
      </div>

      {/* Meta */}
      <div className="text-xs text-gray-600 flex gap-4">
        <span>Data points: {metrics.data_points}</span>
        {metrics.start_date && <span>From: {metrics.start_date}</span>}
        {metrics.end_date && <span>To: {metrics.end_date}</span>}
      </div>
    </div>
  )
}

function FundamentalsTable({ rows }) {
  if (!rows || rows.length === 0) return null
  return (
    <div>
      <h4 className="text-xs text-gray-500 uppercase tracking-wide mb-2">S&amp;P 500 Fundamentals (Kaggle)</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left py-1 pr-3">Ticker</th>
              <th className="text-right py-1 pr-3">P/E</th>
              <th className="text-right py-1 pr-3">P/B</th>
              <th className="text-right py-1 pr-3">ROE</th>
              <th className="text-right py-1 pr-3">Mkt Cap</th>
              <th className="text-left py-1">Sector</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.ticker} className="border-b border-gray-900 hover:bg-gray-800/30">
                <td className="py-1 pr-3 font-mono font-semibold text-gray-200">{r.ticker}</td>
                <td className="text-right py-1 pr-3 text-gray-300">{r.pe_ratio != null ? r.pe_ratio.toFixed(1) : '—'}</td>
                <td className="text-right py-1 pr-3 text-gray-300">{r.pb_ratio != null ? r.pb_ratio.toFixed(2) : '—'}</td>
                <td className={`text-right py-1 pr-3 ${r.roe != null && r.roe > 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {r.roe != null ? `${(r.roe * 100).toFixed(1)}%` : '—'}
                </td>
                <td className="text-right py-1 pr-3 text-gray-400">
                  {r.market_cap != null ? `$${(r.market_cap / 1e9).toFixed(1)}B` : '—'}
                </td>
                <td className="py-1 text-gray-500">{r.sector || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TickerSearchPanel() {
  const [ticker, setTicker] = useState('')
  const [market, setMarket] = useState('us')
  const [period, setPeriod] = useState(365)
  const [benchmark, setBenchmark] = useState('sp500')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!ticker.trim()) return
    setLoading(true); setError(null); setResult(null)
    try {
      const r = await fetch(
        `${BASE_URL}/api/benchmark/ticker/${encodeURIComponent(ticker.trim().toUpperCase())}` +
        `?market=${market}&period_days=${period}&benchmark=${benchmark}`
      )
      const data = await r.json()
      if (data.error) { setError(data.error) } else { setResult(data) }
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
      <h3 className="text-sm font-semibold text-gray-300">Single Ticker vs Benchmark</h3>
      <form onSubmit={handleSearch} className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <input
          value={ticker}
          onChange={e => setTicker(e.target.value)}
          placeholder="AAPL, MSFT…"
          className="col-span-2 sm:col-span-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
        />
        <select value={market} onChange={e => setMarket(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-300">
          {['india','us','europe','japan','korea'].map(m => (
            <option key={m} value={m}>{m.charAt(0).toUpperCase()+m.slice(1)}</option>
          ))}
        </select>
        <select value={period} onChange={e => setPeriod(Number(e.target.value))}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-300">
          <option value={90}>90 days</option>
          <option value={180}>180 days</option>
          <option value={365}>1 year</option>
          <option value={730}>2 years</option>
          <option value={1825}>5 years</option>
        </select>
        <button type="submit" disabled={loading}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded px-3 py-1.5 transition-colors">
          {loading ? 'Loading…' : 'Compare'}
        </button>
      </form>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {result && (
        <div className="space-y-4 pt-2 border-t border-gray-800">
          <MetricsGrid metrics={result} benchmark={result.benchmark} />
          {result.fundamentals && (
            <div className="text-xs text-gray-500">
              <span className="font-medium text-gray-400">Selected S&P 500 indicators: </span>
              {Object.entries(result.fundamentals).slice(0, 8).map(([k, v]) => (
                <span key={k} className="mr-3">{k}: <span className="text-gray-300">{v}</span></span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function BenchmarkPanel({ holdings = [], market = 'us' }) {
  const [benchmark, setBenchmark] = useState('sp500')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [datasetStatus, setDatasetStatus] = useState(null)

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${BASE_URL}/api/benchmark/status`)
      setDatasetStatus(await r.json())
    } catch (_) {}
  }, [])

  const handleCompare = useCallback(async () => {
    if (!holdings.length) { setError('Upload a portfolio first.'); return }
    setLoading(true); setError(null)
    try {
      const r = await fetch(`${BASE_URL}/api/benchmark/portfolio`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ holdings, benchmark }),
      })
      const data = await r.json()
      if (data.error) { setError(data.error) } else { setResult(data) }
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }, [holdings, benchmark])

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">Benchmark Analysis</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Powered by 5 Kaggle datasets — S&P 500 prices, fundamentals, and portfolio reference data
          </p>
        </div>
        <button
          onClick={fetchStatus}
          className="text-xs text-gray-500 hover:text-gray-300 border border-gray-700 rounded px-2 py-1"
        >
          Dataset status
        </button>
      </div>

      {/* Dataset status */}
      {datasetStatus && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-xs space-y-1">
          <div className="font-medium text-gray-300 mb-1">Loaded datasets</div>
          {datasetStatus.datasets?.length > 0
            ? datasetStatus.datasets.map(d => (
                <div key={d} className="flex items-center gap-2">
                  <span className="w-2 h-2 bg-green-500 rounded-full" />
                  <span className="text-gray-400">{d}</span>
                </div>
              ))
            : <p className="text-gray-600">No Kaggle datasets loaded. Run <code>python scripts/download_kaggle_datasets.py</code></p>
          }
          {datasetStatus.sp500_stocks && (
            <div className="text-gray-600 pl-4">
              S&P 500: {datasetStatus.sp500_stocks.total_tickers} tickers
            </div>
          )}
          {datasetStatus.sp500_fundamentals && (
            <div className="text-gray-600 pl-4">
              Fundamentals: {datasetStatus.sp500_fundamentals.tickers} companies ×{' '}
              {datasetStatus.sp500_fundamentals.indicators} indicators
            </div>
          )}
        </div>
      )}

      {/* Portfolio comparison */}
      {holdings.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="text-sm font-semibold text-gray-300">
              Portfolio vs Benchmark ({holdings.length} holdings)
            </h3>
            <select
              value={benchmark}
              onChange={e => setBenchmark(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-300"
            >
              {BENCHMARKS.map(b => <option key={b.id} value={b.id}>{b.label}</option>)}
            </select>
            <button
              onClick={handleCompare}
              disabled={loading}
              className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors"
            >
              {loading ? 'Computing…' : 'Run Analysis'}
            </button>
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          {result && (
            <div className="space-y-6 pt-2 border-t border-gray-800">
              <MetricsGrid metrics={result} benchmark={result.benchmark} />
              {result.holdings_fundamentals?.length > 0 && (
                <FundamentalsTable rows={result.holdings_fundamentals} />
              )}
            </div>
          )}
        </div>
      )}

      {holdings.length === 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-8 text-center space-y-2">
          <div className="text-3xl">📊</div>
          <p className="text-gray-400 font-medium">Upload a portfolio to compare against a benchmark</p>
          <p className="text-sm text-gray-600">
            Once holdings are loaded in the Portfolio panel, come here to compute
            alpha, beta, Sharpe ratio, max drawdown, and S&P 500 fundamentals.
          </p>
        </div>
      )}

      {/* Single ticker search — always available */}
      <TickerSearchPanel />
    </div>
  )
}
