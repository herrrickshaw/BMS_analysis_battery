import { useState } from 'react'

const API = '/api/pricing'

// ── Helpers ───────────────────────────────────────────────────────────────────

const DEMAND_COLORS = {
  low:      'text-emerald-400',
  medium:   'text-yellow-400',
  high:     'text-orange-400',
  critical: 'text-red-400',
  'n/a':    'text-gray-500',
}

const DEMAND_BG = {
  low:      'bg-emerald-950/60 border-emerald-800',
  medium:   'bg-yellow-950/60  border-yellow-800',
  high:     'bg-orange-950/60  border-orange-800',
  critical: 'bg-red-950/60     border-red-800',
  'n/a':    'bg-gray-800/40    border-gray-700',
}

function fmt(currency, amount) {
  const symbols = { INR: '₹', USD: '$', EUR: '€', GBP: '£', JPY: '¥' }
  const sym = symbols[currency] || currency + ' '
  return `${sym}${Number(amount).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

function localDatetimeDefault(daysAhead = 30) {
  const d = new Date()
  d.setDate(d.getDate() + daysAhead)
  return d.toISOString().slice(0, 16)
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function Label({ children }) {
  return <label className="block text-xs text-gray-400 mb-1 font-medium">{children}</label>
}

function Input({ ...props }) {
  return (
    <input
      {...props}
      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100
                 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors"
    />
  )
}

function Select({ children, ...props }) {
  return (
    <select
      {...props}
      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100
                 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors"
    >
      {children}
    </select>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <Label>{label}</Label>
      {children}
    </div>
  )
}

function FactorBar({ label, value, max = 5, accent = 'indigo' }) {
  const pct = Math.min(100, (value / max) * 100)
  const colors = {
    indigo: 'bg-indigo-500',
    yellow: 'bg-yellow-500',
    red:    'bg-red-500',
    emerald:'bg-emerald-500',
    orange: 'bg-orange-500',
  }
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-36 text-gray-400 truncate">{label}</span>
      <div className="flex-1 bg-gray-800 rounded-full h-2">
        <div
          className={`${colors[accent] || colors.indigo} h-2 rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-10 text-right text-gray-300 tabular-nums">{value.toFixed(2)}×</span>
    </div>
  )
}

function ResultCard({ result, currency }) {
  if (!result) return null
  const dl = result.demand_level || 'low'
  return (
    <div className={`rounded-xl border p-5 space-y-4 ${DEMAND_BG[dl]}`}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div>
          {result.route && (
            <div className="text-xs text-gray-400 mb-1">{result.route}</div>
          )}
          <div className="text-3xl font-bold text-white tabular-nums">
            {fmt(currency, result.final_fare)}
          </div>
          {result.base_fare != null && result.base_fare !== result.final_fare && (
            <div className="text-xs text-gray-400 mt-1">
              Base: {fmt(currency, result.base_fare)}
            </div>
          )}
        </div>
        <div className="text-right shrink-0">
          <div className={`text-2xl font-bold tabular-nums ${DEMAND_COLORS[dl]}`}>
            {result.surge_multiplier?.toFixed(2)}×
          </div>
          <div className={`text-xs font-semibold uppercase tracking-wide ${DEMAND_COLORS[dl]}`}>
            {dl} demand
          </div>
        </div>
      </div>

      {/* Key stats row */}
      <div className="flex flex-wrap gap-3">
        {result.days_to_departure != null && (
          <Chip label="Days ahead" value={result.days_to_departure} />
        )}
        {result.days_to_journey != null && (
          <Chip label="Days ahead" value={result.days_to_journey} />
        )}
        {result.fill_rate_pct != null && (
          <Chip label="Fill rate" value={`${result.fill_rate_pct}%`} />
        )}
        {result.booking_status && (
          <Chip label="Status" value={result.booking_status} />
        )}
        {result.eta_minutes != null && (
          <Chip label="ETA" value={`~${result.eta_minutes} min`} />
        )}
        {result.tatkal_premium > 0 && (
          <Chip label="Tatkal" value={`+${fmt(currency, result.tatkal_premium)}`} accent="orange" />
        )}
      </div>

      {/* Breakdown bars */}
      {result.breakdown && Object.keys(result.breakdown).length > 0 && (
        <div className="space-y-1.5 pt-2 border-t border-white/10">
          <div className="text-xs text-gray-500 font-semibold uppercase tracking-wider mb-2">
            Price Factors
          </div>
          {Object.entries(result.breakdown).map(([k, v]) => {
            if (k === 'tatkal_premium') return null
            const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
            const accent = v >= 3 ? 'red' : v >= 2 ? 'orange' : v >= 1.3 ? 'yellow' : 'emerald'
            return <FactorBar key={k} label={label} value={v} max={5} accent={accent} />
          })}
        </div>
      )}
    </div>
  )
}

function Chip({ label, value, accent }) {
  const base = accent === 'orange' ? 'bg-orange-900/40 text-orange-300' : 'bg-gray-800/60 text-gray-200'
  return (
    <div className={`rounded-lg px-3 py-1.5 text-xs ${base}`}>
      <span className="text-gray-500">{label}: </span>
      <span className="font-semibold">{value}</span>
    </div>
  )
}

function ErrorBox({ msg }) {
  return (
    <div className="p-3 bg-red-950/50 border border-red-800 rounded-lg text-red-300 text-sm">
      {msg}
    </div>
  )
}

// ── Flight tab ────────────────────────────────────────────────────────────────

const AIRLINE_MODELS = [
  { value: 'legacy',     label: 'Legacy (Lufthansa / American)', desc: 'Fare-bucket bid-price + booking pace + competitor anchor' },
  { value: 'lcc',        label: 'LCC (Ryanair)',                 desc: 'Load-active / yield-passive — fill plane first, recover via ancillaries' },
  { value: 'continuous', label: 'Continuous (PROS/Amadeus)',      desc: 'Smooth price curve — approximates Lufthansa Request-Specific Pricing' },
]

const MODEL_COLORS = {
  legacy:     'bg-blue-950/50 border-blue-700 text-blue-300',
  lcc:        'bg-orange-950/50 border-orange-700 text-orange-300',
  continuous: 'bg-purple-950/50 border-purple-700 text-purple-300',
}

function FlightForm() {
  const [form, setForm] = useState({
    origin: 'BOM', destination: 'LHR',
    departure_dt: localDatetimeDefault(14),
    seat_class: 'economy',
    seats_available: 45, seats_total: 180,
    base_fare: 350, currency: 'USD',
    airline_model: 'legacy',
    current_bookings: 0, historical_expected: 0,
    competitor_fare: 0, competitor_weight: 0.25,
    ancillary_per_pax: 25,
  })
  const [result, setResult]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const isLCC = form.airline_model === 'lcc'

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${API}/flight`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          seats_available: Number(form.seats_available),
          seats_total: Number(form.seats_total),
          base_fare: Number(form.base_fare),
          current_bookings: Number(form.current_bookings),
          historical_expected: Number(form.historical_expected),
          competitor_fare: Number(form.competitor_fare),
          competitor_weight: Number(form.competitor_weight),
          ancillary_per_pax: Number(form.ancillary_per_pax),
        }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`)
      setResult(await res.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const activeModelMeta = AIRLINE_MODELS.find(m => m.value === form.airline_model)

  return (
    <div className="space-y-5">
      {/* Model selector */}
      <div>
        <Label>Airline pricing model</Label>
        <div className="grid grid-cols-3 gap-2 mt-1">
          {AIRLINE_MODELS.map(m => (
            <button
              key={m.value}
              type="button"
              onClick={() => set('airline_model', m.value)}
              className={`rounded-lg border p-2.5 text-left transition-all text-xs ${
                form.airline_model === m.value
                  ? MODEL_COLORS[m.value] + ' ring-1 ring-current'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'
              }`}
            >
              <div className="font-semibold">{m.label}</div>
              <div className="text-gray-500 mt-0.5 leading-tight">{m.desc}</div>
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={submit} className="grid grid-cols-2 gap-3">
        <Field label="Origin (IATA)">
          <Input value={form.origin} onChange={e => set('origin', e.target.value)} placeholder="BOM" required />
        </Field>
        <Field label="Destination (IATA)">
          <Input value={form.destination} onChange={e => set('destination', e.target.value)} placeholder="LHR" required />
        </Field>
        <Field label="Departure date & time">
          <Input type="datetime-local" value={form.departure_dt} onChange={e => set('departure_dt', e.target.value)} required />
        </Field>
        <Field label={isLCC ? 'Cabin class (N/A for LCC)' : 'Cabin class'}>
          <Select value={form.seat_class} onChange={e => set('seat_class', e.target.value)} disabled={isLCC}>
            {['economy','premium_economy','business','first'].map(c => (
              <option key={c} value={c}>{c.replace('_', ' ').replace(/\b\w/g, x => x.toUpperCase())}</option>
            ))}
          </Select>
        </Field>
        <Field label="Seats available">
          <Input type="number" min={0} value={form.seats_available} onChange={e => set('seats_available', e.target.value)} />
        </Field>
        <Field label="Total seats">
          <Input type="number" min={1} value={form.seats_total} onChange={e => set('seats_total', e.target.value)} />
        </Field>
        <Field label="Base fare">
          <Input type="number" min={0} step="0.01" value={form.base_fare} onChange={e => set('base_fare', e.target.value)} />
        </Field>
        <Field label="Currency">
          <Select value={form.currency} onChange={e => set('currency', e.target.value)}>
            {['USD','EUR','GBP','INR','JPY'].map(c => <option key={c}>{c}</option>)}
          </Select>
        </Field>

        {/* Advanced: booking pace + competitor anchor */}
        <div className="col-span-2">
          <button
            type="button"
            onClick={() => setShowAdvanced(v => !v)}
            className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
          >
            <span>{showAdvanced ? '▾' : '▸'}</span>
            {showAdvanced ? 'Hide' : 'Show'} advanced inputs (booking pace · competitor fare · ancillary)
          </button>
        </div>

        {showAdvanced && (
          <>
            <div className="col-span-2 border-t border-gray-800 pt-3">
              <div className="text-xs text-gray-500 mb-2 font-semibold uppercase tracking-wider">
                Booking Pace (used by Legacy + Continuous models)
              </div>
            </div>
            <Field label="Current bookings on this flight">
              <Input type="number" min={0} value={form.current_bookings} onChange={e => set('current_bookings', e.target.value)} />
            </Field>
            <Field label="Historical expected at same point">
              <Input type="number" min={0} value={form.historical_expected} onChange={e => set('historical_expected', e.target.value)} placeholder="e.g. 80" />
            </Field>

            <div className="col-span-2 border-t border-gray-800 pt-3">
              <div className="text-xs text-gray-500 mb-2 font-semibold uppercase tracking-wider">
                Competitor Anchor (Legacy + Continuous)
              </div>
            </div>
            <Field label="Competitor fare (0 = ignore)">
              <Input type="number" min={0} step="0.01" value={form.competitor_fare} onChange={e => set('competitor_fare', e.target.value)} />
            </Field>
            <Field label="Blend weight (0–1)">
              <Input type="number" min={0} max={1} step="0.05" value={form.competitor_weight} onChange={e => set('competitor_weight', e.target.value)} />
            </Field>

            {isLCC && (
              <>
                <div className="col-span-2 border-t border-gray-800 pt-3">
                  <div className="text-xs text-gray-500 mb-2 font-semibold uppercase tracking-wider">
                    LCC Ancillary Revenue
                  </div>
                </div>
                <div className="col-span-2">
                  <Field label="Ancillary revenue per pax (bags + seat + boarding)">
                    <Input type="number" min={0} step="1" value={form.ancillary_per_pax} onChange={e => set('ancillary_per_pax', e.target.value)} />
                  </Field>
                </div>
              </>
            )}
          </>
        )}

        <div className="col-span-2">
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                       text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {loading ? 'Calculating…' : '✈ Get Flight Price'}
          </button>
        </div>
      </form>

      {error  && <ErrorBox msg={error} />}

      {result && (
        <div className="space-y-3">
          <ResultCard result={result} currency={result.currency} />
          {/* Model notes */}
          {result.model_notes?.length > 0 && (
            <div className="rounded-lg bg-gray-800/40 border border-gray-700 p-3 space-y-1">
              <div className="text-xs text-gray-500 font-semibold uppercase tracking-wider mb-1">Model Logic</div>
              {result.model_notes.map((n, i) => (
                <div key={i} className="text-xs text-gray-400">· {n}</div>
              ))}
              {result.ancillary_estimate > 0 && (
                <div className="text-xs text-orange-400 font-semibold mt-1">
                  Total revenue/pax (ticket + ancillary): {result.currency === 'INR' ? '₹' : result.currency === 'USD' ? '$' : result.currency + ' '}
                  {(result.final_fare + result.ancillary_estimate).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Uber tab ──────────────────────────────────────────────────────────────────

function UberForm() {
  const [form, setForm] = useState({
    distance_km: 12, duration_min: 28,
    vehicle_type: 'economy',
    available_drivers: 8, active_requests: 14,
    weather: 'clear',
    is_special_event: false,
    currency: 'INR',
  })
  const [result, setResult]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${API}/uber`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          distance_km: Number(form.distance_km),
          duration_min: Number(form.duration_min),
          available_drivers: Number(form.available_drivers),
          active_requests: Number(form.active_requests),
        }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`)
      setResult(await res.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-5">
      <form onSubmit={submit} className="grid grid-cols-2 gap-3">
        <Field label="Distance (km)">
          <Input type="number" min={0} step="0.1" value={form.distance_km}
            onChange={e => set('distance_km', e.target.value)} />
        </Field>
        <Field label="Est. duration (min)">
          <Input type="number" min={0} step="1" value={form.duration_min}
            onChange={e => set('duration_min', e.target.value)} />
        </Field>
        <Field label="Vehicle type">
          <Select value={form.vehicle_type} onChange={e => set('vehicle_type', e.target.value)}>
            {['economy','premium','xl','moto','auto','black'].map(t => (
              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
            ))}
          </Select>
        </Field>
        <Field label="Weather">
          <Select value={form.weather} onChange={e => set('weather', e.target.value)}>
            {['clear','cloudy','rain','heavy_rain','storm','snow','fog'].map(w => (
              <option key={w} value={w}>{w.replace('_',' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
            ))}
          </Select>
        </Field>
        <Field label="Available drivers">
          <Input type="number" min={0} value={form.available_drivers}
            onChange={e => set('available_drivers', e.target.value)} />
        </Field>
        <Field label="Active ride requests">
          <Input type="number" min={0} value={form.active_requests}
            onChange={e => set('active_requests', e.target.value)} />
        </Field>
        <Field label="Currency">
          <Select value={form.currency} onChange={e => set('currency', e.target.value)}>
            {['INR','USD','EUR','GBP'].map(c => <option key={c}>{c}</option>)}
          </Select>
        </Field>
        <Field label="Special event?">
          <div className="flex items-center gap-2 mt-2">
            <input
              type="checkbox"
              id="is_event"
              checked={form.is_special_event}
              onChange={e => set('is_special_event', e.target.checked)}
              className="w-4 h-4 rounded accent-indigo-500"
            />
            <label htmlFor="is_event" className="text-sm text-gray-300">Concert / match / festival nearby</label>
          </div>
        </Field>
        <div className="col-span-2">
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                       text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {loading ? 'Calculating…' : '🚗 Get Ride Price'}
          </button>
        </div>
      </form>
      {error  && <ErrorBox msg={error} />}
      {result && <ResultCard result={result} currency={result.currency} />}
    </div>
  )
}

// ── Railway tab ───────────────────────────────────────────────────────────────

function RailwayForm() {
  const [form, setForm] = useState({
    base_fare_per_km: 0.50,
    distance_km: 500,
    journey_dt: localDatetimeDefault(7),
    coach_class: 'SL',
    seats_available: 18, waiting_list: 0,
    total_quota: 72,
    train_type: 'express',
    currency: 'INR',
  })
  const [result, setResult]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${API}/railway`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          base_fare_per_km: Number(form.base_fare_per_km),
          distance_km: Number(form.distance_km),
          seats_available: Number(form.seats_available),
          waiting_list: Number(form.waiting_list),
          total_quota: Number(form.total_quota),
        }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`)
      setResult(await res.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-5">
      <form onSubmit={submit} className="grid grid-cols-2 gap-3">
        <Field label="Base fare / km">
          <Input type="number" min={0} step="0.01" value={form.base_fare_per_km}
            onChange={e => set('base_fare_per_km', e.target.value)} />
        </Field>
        <Field label="Distance (km)">
          <Input type="number" min={1} step="1" value={form.distance_km}
            onChange={e => set('distance_km', e.target.value)} />
        </Field>
        <Field label="Journey date & time">
          <Input type="datetime-local" value={form.journey_dt}
            onChange={e => set('journey_dt', e.target.value)} required />
        </Field>
        <Field label="Train type">
          <Select value={form.train_type} onChange={e => set('train_type', e.target.value)}>
            {['local','passenger','express','superfast','shatabdi','rajdhani','duronto','vande_bharat','tejas','premium'].map(t => (
              <option key={t} value={t}>{t.replace('_',' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
            ))}
          </Select>
        </Field>
        <Field label="Coach class">
          <Select value={form.coach_class} onChange={e => set('coach_class', e.target.value)}>
            {[
              ['2S','2S – Second Sitting'],
              ['SL','SL – Sleeper'],
              ['CC','CC – AC Chair Car'],
              ['3E','3E – AC Economy'],
              ['3A','3A – Third AC'],
              ['2A','2A – Second AC'],
              ['1A','1A – First AC'],
              ['EC','EC – Executive Chair Car'],
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
        <Field label="Seats available">
          <Input type="number" min={0} value={form.seats_available}
            onChange={e => set('seats_available', e.target.value)} />
        </Field>
        <Field label="Waitlist number (0 if none)">
          <Input type="number" min={0} value={form.waiting_list}
            onChange={e => set('waiting_list', e.target.value)} />
        </Field>
        <Field label="Total quota (coach capacity)">
          <Input type="number" min={1} value={form.total_quota}
            onChange={e => set('total_quota', e.target.value)} />
        </Field>
        <div className="col-span-2">
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                       text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {loading ? 'Calculating…' : '🚂 Get Railway Price'}
          </button>
        </div>
      </form>
      {error  && <ErrorBox msg={error} />}
      {result && <ResultCard result={result} currency={result.currency} />}
    </div>
  )
}

// ── Demand model explainer ────────────────────────────────────────────────────

function DemandExplainer() {
  const [subtab, setSubtab] = useState('factors')

  const factorSections = [
    {
      title: '✈ Flight Pricing Factors',
      color: 'indigo',
      rows: [
        ['Days ahead → multiplier', '90+ → 1.0× · 30 → 1.4× · 14 → 2.0× · 3 → 3.2× · same day → 5.0×'],
        ['Seat fill rate', 'Empty → 1.0× · 70% full → 1.8× · 95%+ full → 3.5×'],
        ['Booking pace', 'Under-pace 0.75× · On-track 1.0× · 2× pace → 1.65× (LCC: deeper discounts when lagging)'],
        ['Cabin class', 'Economy 1× · Premium Economy 1.55× · Business 3.2× · First 6×'],
        ['Season', 'Dec/Jan 1.5× · Oct/Nov 1.28× · May/Jun 1.35× · Feb/Sep 1.0×'],
        ['Day of week', 'Fri 1.25× · Sun 1.2× · Mon/Thu 1.1× · Tue–Wed 1.0×'],
        ['Competitor anchor', 'Blends own price toward market rate (default 25% weight)'],
      ],
    },
    {
      title: '🚗 Ride-Share Pricing Factors',
      color: 'yellow',
      rows: [
        ['Demand/supply ratio', '<0.8 → 0.9× · 1.2 → 1.3× · 1.8 → 1.8× · 2.5 → 2.5× (capped 6×)'],
        ['Time of day', 'Morning rush 1.6× · Evening rush 1.7× · Late night 1.3× · Midday 1.1×'],
        ['Weather', 'Clear 1× · Rain 1.4× · Heavy rain 1.8× · Storm 2.5×'],
        ['Special event', 'Concert / match nearby → 1.35×'],
      ],
    },
    {
      title: '🚂 Railway Pricing Factors',
      color: 'emerald',
      rows: [
        ['Availability', 'Plenty → 1.0× · <30% left → 1.6× · Last few → 2.8× · WL1-10 → 1.9×'],
        ['Days to journey', '30+ → 1.0× · 15 → 1.1× · 7 → 1.25× · 4 (Tatkal) → 1.55× · 2 → 2.1×'],
        ['Coach class', '2S 0.65× · SL 1× · CC 1.75× · 3A 2.8× · 2A 4.2× · 1A 7×'],
        ['Train type', 'Local 0.6× · Express 1× · Rajdhani 1.6× · Vande Bharat 1.8×'],
        ['Tatkal premium', '+30% flat charge when ≤3 days to journey'],
        ['Regret', 'WL > 50 → ticket not available'],
      ],
    },
  ]

  const comparisonRows = [
    ['Objective',          'Max revenue/seat', 'Max load factor first', 'Max network yield', 'Max network yield'],
    ['Fare structure',     'Multiplier (4 classes)', 'Single cabin, many price points', '20+ ATPCO fare buckets', 'Continuous (no buckets)'],
    ['Primary signal',     'Days + fill rate', 'Booking pace vs. target', 'Bid price curve', 'Request-specific AI'],
    ['Booking pace',       'Partial (pace factor)', 'Core — cuts fares if lagging', 'Full curve comparison', 'Deep neural network'],
    ['Competitor pricing', 'Anchor blend (optional)', 'Real-time scraping + response', 'Monitored, not auto-blended', 'Real-time competitive AI'],
    ['Overbooking',        'Not modeled', 'Minimal (LCC practice)', 'Full statistical model', 'Full statistical model'],
    ['Ancillary revenue',  'Not modeled', 'Core (~40% of revenue)', 'Modeled (PROS Dynamic Ancillary)', 'Growing'],
    ['Distribution',       'N/A', 'Direct only (no GDS)', 'GDS + direct + metasearch', 'GDS + NDC direct'],
    ['Pricing engine',     'Custom formula', 'Proprietary + external RM', 'PROS Request-Specific + Sabre', 'PROS RM + Sabre CRO'],
    ['Revenue uplift',     'N/A', 'N/A', '5.2% via PROS (2024)', '$500M/yr (AA legacy RM est.)'],
    ['Customer context',   'Not modeled', 'Not modeled', 'Device, loyalty, session data', 'Loyalty tier, booking history'],
    ['Network O&D optim.', 'Not modeled', 'Point-to-point only', 'Full network optimization', 'Full network optimization'],
  ]

  const gapRows = [
    ['Booking pace velocity', 'Added as optional factor', 'Real airlines treat this as the #1 signal — current pace vs. historical curve'],
    ['O&D network effects', 'Not modeled', 'AA/Lufthansa optimize across all connections, not just this flight segment'],
    ['Customer willingness-to-pay', 'Approximated via class multiplier', 'Lufthansa uses device, session time, loyalty status, referral source per request'],
    ['Overbooking model', 'Not modeled', 'AA/Lufthansa statistically oversell based on historical no-show rates'],
    ['Route-specific demand curve', 'Universal formula', 'Real systems have per-route curves built from years of historical O&D data'],
    ['Dynamic ancillary pricing', 'LCC add-on only', 'Lufthansa now dynamically prices bags/seats/upgrades based on trip dimensions'],
    ['Price elasticity by segment', 'Implicit via class mult.', 'Real systems separate business (inelastic) from leisure (elastic) demand pools'],
    ['Real-time competitor scraping', 'Optional anchor input', 'Airlines monitor competitors every few minutes and auto-adjust'],
  ]

  const colorMap = {
    indigo: 'text-indigo-400 border-indigo-700 bg-indigo-950/30',
    yellow: 'text-yellow-400 border-yellow-700 bg-yellow-950/30',
    emerald:'text-emerald-400 border-emerald-700 bg-emerald-950/30',
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-1">
        {[
          { key: 'factors',    label: 'Our Factors' },
          { key: 'comparison', label: 'vs. Real Airlines' },
          { key: 'gaps',       label: 'Model Gaps' },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setSubtab(t.key)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              subtab === t.key
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {subtab === 'factors' && (
        <div className="space-y-4">
          {factorSections.map(s => (
            <div key={s.title} className={`rounded-xl border p-4 ${colorMap[s.color]}`}>
              <div className={`text-sm font-bold mb-3 ${colorMap[s.color].split(' ')[0]}`}>{s.title}</div>
              <table className="w-full text-xs">
                <tbody>
                  {s.rows.map(([k, v]) => (
                    <tr key={k} className="border-t border-white/5">
                      <td className="py-1.5 pr-3 text-gray-400 font-medium w-36 align-top">{k}</td>
                      <td className="py-1.5 text-gray-300">{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      {subtab === 'comparison' && (
        <div className="rounded-xl border border-gray-700 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-800">
                <th className="text-left py-2 px-3 text-gray-400 font-semibold w-36">Dimension</th>
                <th className="text-left py-2 px-3 text-indigo-400 font-semibold">Our Model</th>
                <th className="text-left py-2 px-3 text-orange-400 font-semibold">Ryanair (ULCC)</th>
                <th className="text-left py-2 px-3 text-blue-400 font-semibold">American (Legacy)</th>
                <th className="text-left py-2 px-3 text-purple-400 font-semibold">Lufthansa (PROS)</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map(([dim, ...vals], i) => (
                <tr key={dim} className={i % 2 === 0 ? 'bg-gray-900/40' : 'bg-gray-800/20'}>
                  <td className="py-2 px-3 text-gray-400 font-medium align-top">{dim}</td>
                  {vals.map((v, j) => (
                    <td key={j} className="py-2 px-3 text-gray-300 align-top">{v}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {subtab === 'gaps' && (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">
            These are factors real airline RM systems use that our model approximates or omits. Each gap represents a research area for model improvement.
          </p>
          {gapRows.map(([gap, ours, real]) => (
            <div key={gap} className="rounded-lg border border-gray-700 bg-gray-800/30 p-3">
              <div className="text-xs font-bold text-white mb-1">{gap}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-indigo-400 font-semibold">Our model: </span>
                  <span className="text-gray-400">{ours}</span>
                </div>
                <div>
                  <span className="text-orange-400 font-semibold">Real systems: </span>
                  <span className="text-gray-400">{real}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Root component ────────────────────────────────────────────────────────────

const TABS = [
  { key: 'flight',  label: '✈ Flight',     Component: FlightForm },
  { key: 'uber',    label: '🚗 Ride-Share', Component: UberForm },
  { key: 'railway', label: '🚂 Railway',    Component: RailwayForm },
  { key: 'model',   label: '📊 Demand Model', Component: DemandExplainer },
]

export default function SurgePricing() {
  const [tab, setTab] = useState('flight')
  const Active = TABS.find(t => t.key === tab)?.Component

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white">Surge Pricing Engine</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Multi-factor dynamic pricing · flights · ride-share · railway
          </p>
        </div>
        <div className="text-xs text-gray-600 italic">demand-driven · real-time</div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              tab === t.key
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Active tab content */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5">
        {Active && <Active />}
      </div>
    </div>
  )
}
