import { useCallback, useEffect, useRef, useState } from 'react'
import {
  listFiles, uploadWorkspaceFile, deleteFile,
  previewFile, analyseFile,
} from '../api'
import ScoreBadge from './ScoreBadge'

const MARKETS = [
  { id: 'india',  label: '🇮🇳 India'  },
  { id: 'us',     label: '🇺🇸 US'     },
  { id: 'europe', label: '🇪🇺 Europe' },
  { id: 'japan',  label: '🇯🇵 Japan'  },
  { id: 'korea',  label: '🇰🇷 Korea'  },
  { id: 'china',  label: '🇨🇳 China'  },
]

const ANALYSES = [
  { id: 'darvas',     label: 'Darvas / Buffett', icon: '📈', desc: 'Momentum + quality overlay' },
  { id: 'piotroski',  label: 'Piotroski',         icon: '🏦', desc: '9-point financial strength' },
  { id: 'coffee_can', label: 'Coffee Can',         icon: '☕', desc: 'Buy-and-hold forever' },
  { id: 'portfolio',  label: 'Portfolio P&L',      icon: '💼', desc: 'Holdings with price history, dividends, RSI' },
  { id: 'preview',    label: 'Preview Data',        icon: '👁',  desc: 'Inspect rows and columns' },
]

const EXT_BADGE = {
  csv:  'bg-emerald-900/40 text-emerald-400 border-emerald-800',
  xlsx: 'bg-blue-900/40 text-blue-400 border-blue-800',
  xls:  'bg-blue-900/40 text-blue-400 border-blue-800',
  pdf:  'bg-red-900/40 text-red-400 border-red-800',
}

const SIG_COLORS = {
  BUY:   'text-emerald-400',
  WATCH: 'text-amber-400',
  AVOID: 'text-red-400',
}

function fmt_bytes(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 ** 2).toFixed(1)} MB`
}

function fmt_date(iso) {
  try { return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
  catch { return iso }
}

// ── Screener results mini-table ───────────────────────────────────────────────
function ScanResults({ results }) {
  const [active, setActive] = useState(Object.keys(results)[0])
  const rows = results[active] || []
  const buyRows   = rows.filter(r => r.signal === 'BUY')
  const watchRows = rows.filter(r => r.signal === 'WATCH')

  return (
    <div>
      {/* scan type tabs */}
      <div className="flex gap-2 mb-3 flex-wrap">
        {Object.entries(results).map(([key, arr]) => (
          <button
            key={key}
            onClick={() => setActive(key)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              active === key ? 'bg-indigo-700 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'
            }`}
          >
            {key.replace('_', ' ')} <span className="opacity-60">({arr.length})</span>
          </button>
        ))}
      </div>
      <div className="flex gap-2 mb-3 flex-wrap text-xs">
        {buyRows.length > 0 && (
          <span className="px-2 py-0.5 rounded-full bg-emerald-900/40 text-emerald-400">{buyRows.length} BUY</span>
        )}
        {watchRows.length > 0 && (
          <span className="px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-400">{watchRows.length} WATCH</span>
        )}
        <span className="px-2 py-0.5 rounded-full bg-gray-800 text-gray-500">{rows.length} total</span>
      </div>
      <div className="overflow-x-auto max-h-96 overflow-y-auto rounded-lg border border-gray-800">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-900 border-b border-gray-800">
            <tr>
              {['Company','Ticker','Signal','Score','CMP','PE','ROE','RSI'].map(h => (
                <th key={h} className="px-3 py-2 text-left text-gray-500 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows
              .sort((a, b) => {
                const order = { BUY: 0, WATCH: 1, AVOID: 2 }
                return (order[a.signal] ?? 3) - (order[b.signal] ?? 3) || (b.score ?? 0) - (a.score ?? 0)
              })
              .map((r, i) => (
                <tr key={i} className="border-b border-gray-800/40 hover:bg-gray-800/30">
                  <td className="px-3 py-2 text-gray-200 font-medium max-w-[140px] truncate">{r.name || '—'}</td>
                  <td className="px-3 py-2 font-mono text-gray-400">{r.ticker || '—'}</td>
                  <td className={`px-3 py-2 font-bold ${SIG_COLORS[r.signal] ?? 'text-gray-500'}`}>{r.signal || '—'}</td>
                  <td className="px-3 py-2">
                    <ScoreBadge score={r.score ?? 0} maxScore={r.max_score ?? 10} signal={r.signal} scanType={active} />
                  </td>
                  <td className="px-3 py-2 font-mono text-gray-300">{r.cmp != null ? Number(r.cmp).toLocaleString() : '—'}</td>
                  <td className="px-3 py-2 font-mono text-gray-400">{r.pe != null ? Number(r.pe).toFixed(1) : '—'}</td>
                  <td className="px-3 py-2 font-mono text-gray-400">{r.roe != null ? `${Number(r.roe).toFixed(1)}%` : '—'}</td>
                  <td className="px-3 py-2 font-mono text-gray-400">{r.rsi != null ? Number(r.rsi).toFixed(1) : '—'}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Portfolio P&L results ─────────────────────────────────────────────────────
function PortfolioResults({ data }) {
  const { holdings, summary } = data
  const pnlColor = (v) => v == null ? 'text-gray-400' : v >= 0 ? 'text-emerald-400' : 'text-red-400'

  return (
    <div>
      {/* summary */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          {[
            { label: 'Total Cost',    value: summary.total_cost_basis,     prefix: '' },
            { label: 'Current Value', value: summary.total_current_value,  prefix: '' },
            { label: 'Unrealised P&L', value: summary.total_unrealised_pnl, prefix: '' },
            { label: 'Total Return %', value: summary.total_return_pct,    suffix: '%' },
          ].map(({ label, value, prefix = '', suffix = '' }) => (
            <div key={label} className="bg-gray-800 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-0.5">{label}</p>
              <p className={`text-sm font-bold font-mono ${pnlColor(value)}`}>
                {value != null ? `${prefix}${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}` : '—'}
              </p>
            </div>
          ))}
        </div>
      )}
      <div className="overflow-x-auto max-h-96 overflow-y-auto rounded-lg border border-gray-800">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-900 border-b border-gray-800">
            <tr>
              {['Stock','Ticker','Qty','Buy Price','Current','P&L','P&L %','RSI'].map(h => (
                <th key={h} className="px-3 py-2 text-left text-gray-500 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {holdings.map((h, i) => (
              <tr key={i} className="border-b border-gray-800/40 hover:bg-gray-800/30">
                <td className="px-3 py-2 text-gray-200 font-medium max-w-[130px] truncate">{h.name || '—'}</td>
                <td className="px-3 py-2 font-mono text-gray-400">{h.yf_ticker}</td>
                <td className="px-3 py-2 font-mono text-gray-400">{h.quantity ?? '—'}</td>
                <td className="px-3 py-2 font-mono text-gray-300">{h.purchase_price != null ? Number(h.purchase_price).toLocaleString() : '—'}</td>
                <td className="px-3 py-2 font-mono text-gray-200">{h.current_price != null ? Number(h.current_price).toLocaleString() : '—'}</td>
                <td className={`px-3 py-2 font-mono font-bold ${pnlColor(h.unrealised_pnl)}`}>
                  {h.unrealised_pnl != null ? Number(h.unrealised_pnl).toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'}
                </td>
                <td className={`px-3 py-2 font-mono font-bold ${pnlColor(h.pnl_pct)}`}>
                  {h.pnl_pct != null ? `${Number(h.pnl_pct).toFixed(1)}%` : '—'}
                </td>
                <td className="px-3 py-2 font-mono text-gray-400">{h.rsi != null ? Number(h.rsi).toFixed(1) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Data preview ──────────────────────────────────────────────────────────────
function PreviewResults({ data }) {
  const { columns, preview, total_rows } = data
  return (
    <div>
      <p className="text-xs text-gray-500 mb-2">{total_rows} rows · {columns.length} columns</p>
      <div className="overflow-x-auto max-h-80 overflow-y-auto rounded-lg border border-gray-800">
        <table className="text-xs">
          <thead className="sticky top-0 bg-gray-900 border-b border-gray-800">
            <tr>
              {columns.map(c => (
                <th key={c} className="px-3 py-2 text-left text-gray-500 font-medium whitespace-nowrap">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.map((row, i) => (
              <tr key={i} className="border-b border-gray-800/40 hover:bg-gray-800/30">
                {columns.map(c => (
                  <td key={c} className="px-3 py-2 text-gray-300 whitespace-nowrap max-w-[160px] truncate">{String(row[c] ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function FileWorkspace() {
  const inputRef = useRef()
  const [files,    setFiles]    = useState([])
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selected, setSelected] = useState(null)     // file id
  const [market,   setMarket]   = useState('india')
  const [loading,  setLoading]  = useState(false)
  const [result,   setResult]   = useState(null)     // { type, data }
  const [error,    setError]    = useState(null)

  const refresh = useCallback(async () => {
    try { const d = await listFiles(); setFiles(d.files) }
    catch { /* cassandra/filesystem offline */ }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleDrop = useCallback(async (file) => {
    if (!file) return
    setUploading(true); setError(null)
    try {
      await uploadWorkspaceFile(file)
      await refresh()
    } catch (e) { setError(e.message) }
    finally { setUploading(false) }
  }, [refresh])

  const handleDelete = async (fid) => {
    try { await deleteFile(fid); setFiles(f => f.filter(x => x.id !== fid)); if (selected === fid) { setSelected(null); setResult(null) } }
    catch (e) { setError(e.message) }
  }

  const runAnalysis = async (analysisId) => {
    if (!selected) return
    setLoading(true); setError(null); setResult(null)
    try {
      if (analysisId === 'preview') {
        const d = await previewFile(selected)
        setResult({ type: 'preview', data: d })
      } else if (analysisId === 'portfolio') {
        const d = await analyseFile(selected, 'portfolio', market)
        setResult({ type: 'portfolio', data: d })
      } else {
        const d = await analyseFile(selected, analysisId, market)
        setResult({ type: 'screener', data: d.results })
      }
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  const selectedFile = files.find(f => f.id === selected)

  return (
    <div className="flex gap-4 min-h-[600px]">

      {/* ── Left: file list + upload ─────────────────────────────────────── */}
      <div className="w-64 shrink-0 flex flex-col gap-3">

        {/* upload zone */}
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); handleDrop(e.dataTransfer.files[0]) }}
          className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-all ${
            dragging
              ? 'border-indigo-500 bg-indigo-950/30 scale-[1.01]'
              : 'border-gray-700 hover:border-gray-600 hover:bg-gray-900/60'
          }`}
        >
          {uploading ? (
            <div className="flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin" />
              <p className="text-xs text-indigo-400">Uploading…</p>
            </div>
          ) : (
            <>
              <div className="text-2xl mb-1">📂</div>
              <p className="text-xs text-gray-300 font-medium">Drop file here</p>
              <p className="text-xs text-gray-500 mt-0.5">or <span className="text-indigo-400">browse</span></p>
              <p className="text-xs text-gray-600 mt-1">CSV · Excel · PDF</p>
            </>
          )}
        </div>
        <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls,.pdf" className="hidden"
          onChange={(e) => handleDrop(e.target.files[0])} />

        {/* file list */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden flex-1">
          <div className="px-3 py-2.5 border-b border-gray-800">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Uploaded Files
              {files.length > 0 && <span className="ml-2 text-gray-600 normal-case">({files.length})</span>}
            </h3>
          </div>

          {files.length === 0 ? (
            <div className="p-4 text-center text-gray-600 text-xs">No files yet</div>
          ) : (
            <div className="divide-y divide-gray-800/60 max-h-[420px] overflow-y-auto">
              {files.map(f => (
                <div
                  key={f.id}
                  onClick={() => { setSelected(f.id); setResult(null); setError(null) }}
                  className={`px-3 py-2.5 cursor-pointer transition-colors group ${
                    selected === f.id
                      ? 'bg-indigo-950/40 border-l-2 border-indigo-500'
                      : 'hover:bg-gray-800/50 border-l-2 border-transparent'
                  }`}
                >
                  <div className="flex items-start justify-between gap-1">
                    <div className="min-w-0">
                      <p className="text-xs text-gray-200 font-medium truncate" title={f.label}>{f.label}</p>
                      <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                        <span className={`px-1.5 py-px rounded text-xs border uppercase font-mono ${EXT_BADGE[f.ext] ?? 'bg-gray-800 text-gray-500 border-gray-700'}`}>
                          {f.ext}
                        </span>
                        <span className="text-xs text-gray-600">{fmt_bytes(f.size_bytes)}</span>
                      </div>
                      <p className="text-xs text-gray-700 mt-0.5">{fmt_date(f.uploaded_at)}</p>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(f.id) }}
                      className="text-gray-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 text-sm shrink-0 mt-0.5"
                      title="Delete"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Right: analysis panel ────────────────────────────────────────── */}
      <div className="flex-1 min-w-0">
        {!selected ? (
          <div className="h-full bg-gray-900 rounded-xl border border-gray-800 flex flex-col items-center justify-center text-center p-8">
            <div className="text-4xl mb-3">📁</div>
            <p className="text-gray-400 font-medium">Select a file to analyse</p>
            <p className="text-gray-600 text-sm mt-1">Upload a CSV, Excel, or PDF on the left, then choose an analysis type</p>
          </div>
        ) : (
          <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden flex flex-col">

            {/* file header */}
            <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-100 truncate">{selectedFile?.label}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {fmt_bytes(selectedFile?.size_bytes ?? 0)} · uploaded {fmt_date(selectedFile?.uploaded_at ?? '')}
                </p>
              </div>
              {/* market selector */}
              <select
                value={market}
                onChange={e => setMarket(e.target.value)}
                className="text-xs bg-gray-800 border border-gray-700 text-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:border-indigo-500 shrink-0"
              >
                {MARKETS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
              </select>
            </div>

            {/* analysis buttons */}
            <div className="px-4 py-3 border-b border-gray-800">
              <p className="text-xs text-gray-500 mb-2 uppercase tracking-wider font-semibold">Run Analysis</p>
              <div className="flex gap-2 flex-wrap">
                {ANALYSES.map(a => (
                  <button
                    key={a.id}
                    onClick={() => runAnalysis(a.id)}
                    disabled={loading}
                    title={a.desc}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-xs font-medium text-gray-200 transition-colors"
                  >
                    <span>{a.icon}</span>
                    {a.label}
                  </button>
                ))}
              </div>
            </div>

            {/* results area */}
            <div className="p-4 flex-1 overflow-auto">
              {error && (
                <div className="mb-3 p-3 bg-red-950/40 border border-red-800 rounded-lg text-red-300 text-sm flex justify-between">
                  <span>{error}</span>
                  <button onClick={() => setError(null)} className="ml-3 text-red-500 hover:text-red-400">×</button>
                </div>
              )}

              {loading && (
                <div className="flex flex-col items-center justify-center py-12 gap-3">
                  <div className="w-7 h-7 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin" />
                  <p className="text-gray-400 text-sm">Running analysis…</p>
                </div>
              )}

              {!loading && !result && !error && (
                <div className="text-center py-12 text-gray-600 text-sm">
                  Choose an analysis type above to run
                </div>
              )}

              {!loading && result && (
                <div>
                  {result.type === 'screener' && <ScanResults results={result.data} />}
                  {result.type === 'portfolio' && <PortfolioResults data={result.data} />}
                  {result.type === 'preview'   && <PreviewResults  data={result.data} />}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
