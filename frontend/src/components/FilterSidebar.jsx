const DEFAULT_FILTERS = {
  signals: ['BUY', 'WATCH', 'AVOID'],
  minMarketCap: 0,
  maxPE: 200,
  minROE: 0,
  maxDE: 10,
  minCompleteness: 0,
}

function Slider({ label, value, min, max, step = 1, onChange, fmt }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-400">{label}</span>
        <span className="text-gray-300 font-mono">{fmt ? fmt(value) : value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none bg-gray-700 cursor-pointer"
      />
    </div>
  )
}

export default function FilterSidebar({ filters, onChange }) {
  const set = (key, val) => onChange((prev) => ({ ...prev, [key]: val }))

  const toggleSignal = (s) => {
    const cur = filters.signals
    set('signals', cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s])
  }

  const signalColor = { BUY: 'bg-emerald-600', WATCH: 'bg-amber-500', AVOID: 'bg-red-600' }

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">Filters</h3>
      <div className="space-y-5">
        <div>
          <p className="text-xs text-gray-400 mb-2">Signal</p>
          <div className="flex gap-1.5">
            {['BUY', 'WATCH', 'AVOID'].map((s) => (
              <button
                key={s}
                onClick={() => toggleSignal(s)}
                className={`flex-1 py-1 rounded text-xs font-bold transition-opacity ${signalColor[s]} text-white ${
                  filters.signals.includes(s) ? 'opacity-100' : 'opacity-25'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <Slider
          label="Min Market Cap (Cr)"
          value={filters.minMarketCap}
          min={0} max={50000} step={500}
          onChange={(v) => set('minMarketCap', v)}
          fmt={(v) => v === 0 ? 'Any' : `₹${v.toLocaleString()}`}
        />
        <Slider
          label="Max P/E"
          value={filters.maxPE}
          min={0} max={200} step={5}
          onChange={(v) => set('maxPE', v)}
          fmt={(v) => v >= 200 ? 'Any' : v}
        />
        <Slider
          label="Min ROE (%)"
          value={filters.minROE}
          min={0} max={50} step={1}
          onChange={(v) => set('minROE', v)}
          fmt={(v) => `${v}%`}
        />
        <Slider
          label="Max D/E"
          value={filters.maxDE}
          min={0} max={5} step={0.1}
          onChange={(v) => set('maxDE', v)}
          fmt={(v) => v >= 5 ? 'Any' : v.toFixed(1)}
        />
        <Slider
          label="Min Data Completeness"
          value={filters.minCompleteness}
          min={0} max={100} step={5}
          onChange={(v) => set('minCompleteness', v)}
          fmt={(v) => `${v}%`}
        />

        <button
          onClick={() => onChange(DEFAULT_FILTERS)}
          className="w-full py-1.5 text-xs rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 transition-colors"
        >
          Reset Filters
        </button>
      </div>
    </div>
  )
}
