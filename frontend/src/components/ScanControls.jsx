const SCAN_META = {
  darvas:     { label: 'Darvas Box',        sub: 'Price momentum + Buffett quality' },
  piotroski:  { label: 'Piotroski F-Score', sub: '9-point financial strength' },
  coffee_can: { label: 'Coffee Can',        sub: 'Buy & hold forever' },
}

export default function ScanControls({ scans, activeScan, onScan, onSetActive, loading, hasData }) {
  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Scan Engines
      </h3>
      <div className="space-y-2">
        {scans.map((scan) => {
          const meta = SCAN_META[scan]
          const isActive = activeScan === scan
          return (
            <div
              key={scan}
              onClick={() => hasData && onSetActive(scan)}
              className={`rounded-lg p-3 border transition-all ${
                isActive
                  ? 'bg-indigo-950/60 border-indigo-700 cursor-pointer'
                  : 'border-gray-800 hover:border-gray-700 cursor-pointer'
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-200">{meta.label}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{meta.sub}</p>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); hasData && !loading && onScan(scan) }}
                  disabled={!hasData || loading}
                  className="text-xs px-2.5 py-1 rounded-md bg-indigo-700 hover:bg-indigo-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-white"
                >
                  Run
                </button>
              </div>
            </div>
          )
        })}
        <button
          onClick={() => !loading && hasData && onScan('all')}
          disabled={!hasData || loading}
          className="w-full mt-1 py-2 rounded-lg bg-emerald-700 hover:bg-emerald-600 disabled:opacity-30 disabled:cursor-not-allowed text-sm font-semibold text-white transition-colors"
        >
          {loading ? 'Scanning...' : 'Run All Scans'}
        </button>
        {!hasData && (
          <p className="text-xs text-gray-600 text-center mt-1">Upload data to enable</p>
        )}
      </div>
    </div>
  )
}
