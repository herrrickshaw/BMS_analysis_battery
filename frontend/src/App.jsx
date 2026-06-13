import { useCallback, useState } from 'react'
import Header        from './components/Header'
import MarketTabs    from './components/MarketTabs'
import UploadPanel   from './components/UploadPanel'
import ScanControls  from './components/ScanControls'
import ResultsTable  from './components/ResultsTable'
import FilterSidebar from './components/FilterSidebar'
import LivePanel     from './components/LivePanel'
import ComparisonTable from './components/ComparisonTable'
import SectorBenchmarks from './components/SectorBenchmarks'
import {
  uploadFile, runScan, exportResults,
  fetchLiveData, scanLiveData, compareLiveData,
} from './api'


const MARKETS = [
  { id: 'nse_largecap', label: 'NSE Large Cap' },
  { id: 'nse_midcap',   label: 'NSE Mid Cap' },
  { id: 'nse_smallcap', label: 'NSE Small Cap' },
  { id: 'bse',          label: 'BSE' },
  { id: 'european',     label: 'European' },
]

const SCANS = ['darvas', 'piotroski', 'coffee_can']

const DEFAULT_FILTERS = {
  signals: ['BUY', 'WATCH', 'AVOID'],
  minMarketCap: 0,
  maxPE: 200,
  minROE: 0,
  maxDE: 10,
  minCompleteness: 0,
}

// viewMode: 'screener_scan' | 'live_scan' | 'compare'
export default function App() {
  const [activeMarket, setActiveMarket] = useState('nse_largecap')
  const [activeScan,   setActiveScan]   = useState('darvas')
  const [viewMode,     setViewMode]     = useState('screener_scan')

  // Screener CSV scan results: { market: { scanType: [...] } }
  const [screenerResults, setScreenerResults] = useState({})
  // Live scan results: { market: { scanType: [...] } }
  const [liveResults,     setLiveResults]     = useState({})
  // Comparison data: { market: { summary, comparisons } }
  const [compareData,     setCompareData]     = useState({})

  const [uploadedMarkets, setUploaded]   = useState(new Set())
  const [liveMarkets,     setLiveReady]  = useState(new Set())
  const [fetchStatus,     setFetchStatus] = useState({}) // { market: {...} }
  const [loading,         setLoading]    = useState(false)
  const [error,           setError]      = useState(null)
  const [filters,         setFilters]    = useState(DEFAULT_FILTERS)

  // ── Screener CSV upload ──────────────────────────────────────────────────
  const handleUpload = useCallback(async (file) => {
    setLoading(true); setError(null)
    try {
      await uploadFile(activeMarket, file)
      setUploaded(prev => new Set([...prev, activeMarket]))
      setViewMode('screener_scan')
    } catch (e) { setError(e.message) }
    finally    { setLoading(false) }
  }, [activeMarket])

  // ── Screener scan ────────────────────────────────────────────────────────
  const handleScan = useCallback(async (scanType) => {
    if (!uploadedMarkets.has(activeMarket)) {
      setError('Upload a CSV for this market first.')
      return
    }
    setLoading(true); setError(null); setViewMode('screener_scan')
    try {
      const data = await runScan(activeMarket, scanType)
      setScreenerResults(prev => ({
        ...prev,
        [activeMarket]: { ...(prev[activeMarket] || {}), ...data.results },
      }))
      if (scanType !== 'all') setActiveScan(scanType)
    } catch (e) { setError(e.message) }
    finally    { setLoading(false) }
  }, [activeMarket, uploadedMarkets])

  // ── Live fetch ───────────────────────────────────────────────────────────
  const handleLiveFetch = useCallback(async (indexKey) => {
    setLoading(true); setError(null)
    setFetchStatus(prev => ({ ...prev, [activeMarket]: { status: 'fetching' } }))
    try {
      const resp = await fetchLiveData(activeMarket, indexKey || null)
      setFetchStatus(prev => ({
        ...prev,
        [activeMarket]: { status: 'done', total: resp.requested, done: resp.fetched, errors: resp.errors },
      }))
      setLiveReady(prev => new Set([...prev, activeMarket]))
    } catch (e) {
      setFetchStatus(prev => ({ ...prev, [activeMarket]: { status: 'error', error: e.message } }))
      setError(e.message)
    }
    finally { setLoading(false) }
  }, [activeMarket])

  // ── Live scan ────────────────────────────────────────────────────────────
  const handleLiveScan = useCallback(async () => {
    setLoading(true); setError(null); setViewMode('live_scan')
    try {
      const data = await scanLiveData(activeMarket, 'all')
      setLiveResults(prev => ({
        ...prev,
        [activeMarket]: { ...(prev[activeMarket] || {}), ...data.results },
      }))
    } catch (e) { setError(e.message); setViewMode('screener_scan') }
    finally    { setLoading(false) }
  }, [activeMarket])

  // ── Compare ──────────────────────────────────────────────────────────────
  const handleCompare = useCallback(async () => {
    setLoading(true); setError(null); setViewMode('compare')
    try {
      const data = await compareLiveData(activeMarket)
      setCompareData(prev => ({ ...prev, [activeMarket]: data }))
    } catch (e) { setError(e.message); setViewMode('screener_scan') }
    finally    { setLoading(false) }
  }, [activeMarket])

  const handleExport = useCallback(() => {
    exportResults(activeMarket, activeScan)
  }, [activeMarket, activeScan])

  // ── Derive current data for the view ────────────────────────────────────
  const activeLabel = MARKETS.find(m => m.id === activeMarket)?.label || activeMarket

  const screenerScanResults = screenerResults[activeMarket]?.[activeScan] || []
  const liveScanResults     = liveResults[activeMarket]?.[activeScan]     || []
  const cmpData             = compareData[activeMarket]

  const applyFilters = (rows) => rows.filter(r => {
    if (!filters.signals.includes(r.signal))            return false
    if (r.market_cap != null && r.market_cap < filters.minMarketCap)  return false
    if (r.pe != null && filters.maxPE < 200 && r.pe > filters.maxPE)  return false
    if (r.roe != null && r.roe < filters.minROE)                       return false
    if (r.debt_to_equity != null && filters.maxDE < 10 && r.debt_to_equity > filters.maxDE) return false
    if ((r.completeness ?? 0) < filters.minCompleteness)               return false
    return true
  })

  const displayResults = viewMode === 'live_scan'
    ? applyFilters(liveScanResults)
    : applyFilters(screenerScanResults)

  const displayLabel = viewMode === 'live_scan' ? `${activeScan} · Live` : activeScan

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <Header />

      <div className="max-w-screen-2xl mx-auto px-4 py-4 space-y-4">
        <MarketTabs
          markets={MARKETS}
          active={activeMarket}
          onChange={m => { setActiveMarket(m); setViewMode('screener_scan') }}
          uploaded={uploadedMarkets}
        />

        {error && (
          <div className="p-3 bg-red-950/50 border border-red-800 rounded-lg text-red-300 text-sm flex items-start justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="ml-3 text-red-500 hover:text-red-400 font-bold flex-shrink-0">×</button>
          </div>
        )}

        {/* View mode toggle */}
        <div className="flex items-center gap-1">
            {[
              { key: 'screener_scan', label: 'Screener Scan', disabled: screenerScanResults.length === 0 },
              { key: 'live_scan',     label: 'Live Scan',     disabled: liveScanResults.length === 0 },
              { key: 'compare',       label: 'Compare',       disabled: !cmpData },
              { key: 'sectors',       label: 'Sector Benchmarks', disabled: false },
            ].map(btn => (
              <button
                key={btn.key}
                onClick={() => !btn.disabled && setViewMode(btn.key)}
                disabled={btn.disabled}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  viewMode === btn.key
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-gray-200 disabled:opacity-30 disabled:cursor-not-allowed'
                }`}
              >
                {btn.label}
              </button>
            ))}
            <span className="text-xs text-gray-600 ml-2">· {activeLabel}</span>
          </div>

        <div className="grid grid-cols-12 gap-4">
          {/* Sidebar */}
          <div className="col-span-12 lg:col-span-3 space-y-4">
            <UploadPanel
              onUpload={handleUpload}
              loading={loading}
              marketLabel={activeLabel}
            />
            <ScanControls
              scans={SCANS}
              activeScan={activeScan}
              onScan={handleScan}
              onSetActive={setActiveScan}
              loading={loading}
              hasData={uploadedMarkets.has(activeMarket)}
            />
            <LivePanel
              market={activeMarket}
              hasScreenerData={uploadedMarkets.has(activeMarket)}
              hasLiveData={liveMarkets.has(activeMarket)}
              fetchStatus={fetchStatus[activeMarket]}
              viewMode={viewMode}
              onFetch={handleLiveFetch}
              onCompare={handleCompare}
              onScanLive={handleLiveScan}
            />
            <FilterSidebar filters={filters} onChange={setFilters} />
          </div>

          {/* Main content */}
          <div className="col-span-12 lg:col-span-9">
            {viewMode === 'sectors' ? (
              <SectorBenchmarks />
            ) : viewMode === 'compare' ? (
              <ComparisonTable
                data={cmpData?.comparisons}
                summary={cmpData?.summary}
                loading={loading}
              />
            ) : (
              <ResultsTable
                results={displayResults}
                scanType={activeScan}
                onExport={handleExport}
                loading={loading}
                sourceLabel={viewMode === 'live_scan' ? 'Live (yfinance)' : 'Screener.in'}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
