import { useState } from 'react'

const SOURCES = [
  {
    id: 'screener',
    name: 'Screener.in',
    badge: 'bg-blue-900/40 text-blue-300 border border-blue-800',
    dot: 'bg-blue-400',
    type: 'Fundamental snapshot (user-exported CSV)',
    update: 'Point-in-time when you export',
    strengths: [
      'Complete Indian financials — Revenue, PAT, OPM, ROCE, Promoter holding, Pledging',
      'Adjusted figures: restated for splits, bonuses, and accounting changes',
      'Piotroski score computed by Screener (can be passed through directly)',
      'Reliable D/E definition: financial debt ÷ equity (excludes operating liabilities)',
    ],
    caveats: [
      'Static — data is as of your export date, not live',
      'No intraday price or volume (CMP and volume are end-of-day snapshots)',
      'Sector/industry label varies by user; not standardised across exports',
      'International markets not supported',
    ],
  },
  {
    id: 'yfinance',
    name: 'yfinance (Yahoo Finance)',
    badge: 'bg-violet-900/40 text-violet-300 border border-violet-800',
    dot: 'bg-violet-400',
    type: 'Live market data via Python library',
    update: 'Real-time price; fundamentals updated quarterly',
    strengths: [
      'Live CMP, 52W High/Low, and volume fetched on demand',
      'Global coverage — NSE (.NS), BSE (.BO), US, European, Asian exchanges',
      'Free and no API key required',
      'Institutional/insider holding % available for all markets',
    ],
    caveats: [
      'D/E = total liabilities ÷ equity — inflated vs Screener\'s financial-debt-only measure (e.g. TCS shows ~10x here vs ~0 on Screener)',
      'Percent fields (ROE, margins) returned as decimals — the app multiplies by 100, but source data quality varies',
      'Market cap in absolute INR (÷ 10M to get Cr) — rounding introduces small errors',
      'Data for small/mid caps can be stale or missing; failures silently excluded',
      'Rate-limited: fetching 200+ stocks takes 2–5 minutes; NIFTY 500 ≈ 5 min',
      'Not audited — figures may differ from exchange filings',
    ],
  },
  {
    id: 'damodaran',
    name: 'Aswath Damodaran — NYU Stern',
    badge: 'bg-amber-900/40 text-amber-300 border border-amber-800',
    dot: 'bg-amber-400',
    type: 'Annual sector-level benchmark aggregates',
    update: 'Updated once a year (January); current dataset: Jan 2025',
    strengths: [
      'Sector PE, forward PE, PEG benchmarks by industry for India, US, and Europe',
      'Margins (gross, operating, net) and ROE aggregated across all listed firms in each sector',
      'Market D/E and historical revenue / earnings CAGR (5-year)',
      'Academically rigorous — used as the reference for the Darvas sector-PE criterion (C9)',
      'Covers 96 industry groups per region; reliable for relative valuation context',
    ],
    caveats: [
      'Aggregates, not individual stocks — cannot be used for company-level comparison',
      'Annual snapshot: sector multiples shift significantly between publication dates',
      'Indian industry names (e.g. "Drugs (Pharmaceutical)") mapped to Screener sectors via fuzzy match — occasional misclassification',
      'D/E methodology may differ from both Screener and yfinance definitions',
      'Not suitable for intraday or short-term trading decisions',
    ],
  },
]

const DIFF_TABLE = [
  { metric: 'D/E Ratio',          screener: 'Financial debt ÷ equity\n(conservative)',         yfinance: 'Total liabilities ÷ equity\n(inflated; ×5–20 for asset-heavy firms)', damodaran: 'Market D/E (market value of debt ÷ equity)' },
  { metric: 'ROE %',              screener: 'PAT ÷ Avg. Net Worth\n(TTM, Screener-adjusted)',  yfinance: 'Net income ÷ shareholders equity\n(single period, unadjusted)',           damodaran: 'Aggregated net income ÷ aggregated book equity\n(sector total)' },
  { metric: 'Operating Margin',   screener: 'EBIT ÷ Revenue (OPM)\n(Screener-computed)',        yfinance: 'operatingMargins from Yahoo\n(methodology unclear)',                      damodaran: 'Pre-tax, pre-SBC operating margin\n(sector aggregate)' },
  { metric: 'Promoter / Insider', screener: 'Promoter holding %\n(SEBI filing)',                yfinance: 'heldPercentInsiders\n(SEC/exchange; not promoter concept for India)',    damodaran: 'Not available at company level' },
  { metric: 'Market Cap',         screener: 'Rs. Crore\n(end-of-day)',                          yfinance: 'Absolute INR (÷ 10M → Cr)\nsmall rounding errors',                       damodaran: 'Aggregated across all sector firms\n(USD or local currency)' },
  { metric: 'Price / CMP',        screener: 'Snapshot at export time',                          yfinance: 'Live (fetched on demand)',                                               damodaran: 'N/A — aggregate multiples only' },
  { metric: 'Sector PE',          screener: 'Not provided\n(user must supply sector_pe)',       yfinance: 'trailingPE of the individual stock',                                    damodaran: 'Sector trailing & forward PE\n(used for Darvas C9 benchmark)' },
]

function DotBadge({ color, label }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${color}`} />
      <span>{label}</span>
    </span>
  )
}

export default function DisclaimerModal() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-xs text-gray-600 hover:text-gray-400 underline underline-offset-2 transition-colors"
      >
        Data sources &amp; disclaimers
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-12 bg-black/70 backdrop-blur-sm overflow-y-auto">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-4xl shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
              <div>
                <h2 className="text-base font-bold text-gray-100">Data Sources &amp; Disclaimers</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  This tool aggregates data from three independent sources. Each has different methodologies, update frequencies, and coverage.
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-gray-500 hover:text-gray-300 text-xl font-mono leading-none ml-4"
              >×</button>
            </div>

            <div className="px-6 py-5 space-y-6 max-h-[78vh] overflow-y-auto">

              {/* General disclaimer */}
              <div className="bg-red-950/30 border border-red-900/50 rounded-lg px-4 py-3 text-xs text-red-300 leading-relaxed">
                <strong className="text-red-200">Not financial advice.</strong> All data is provided for research and educational purposes only.
                Figures may be delayed, incorrect, or methodologically inconsistent across sources.
                Do not make investment decisions based solely on this tool. Always verify against official exchange filings.
              </div>

              {/* Per-source cards */}
              {SOURCES.map(s => (
                <div key={s.id} className="rounded-xl border border-gray-800 overflow-hidden">
                  <div className="flex items-center gap-3 px-4 py-3 bg-gray-800/50">
                    <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${s.badge}`}>
                      {s.name}
                    </span>
                    <span className="text-xs text-gray-400">{s.type}</span>
                    <span className="ml-auto text-xs text-gray-600 italic">{s.update}</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 px-4 py-4">
                    <div>
                      <p className="text-xs font-semibold text-emerald-400 mb-2">Strengths</p>
                      <ul className="space-y-1.5">
                        {s.strengths.map((str, i) => (
                          <li key={i} className="flex gap-2 text-xs text-gray-400 leading-relaxed">
                            <span className="text-emerald-500 mt-0.5 flex-shrink-0">✓</span>
                            <span>{str}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-amber-400 mb-2">Caveats &amp; Known Differences</p>
                      <ul className="space-y-1.5">
                        {s.caveats.map((c, i) => (
                          <li key={i} className="flex gap-2 text-xs text-gray-400 leading-relaxed">
                            <span className="text-amber-500 mt-0.5 flex-shrink-0">⚠</span>
                            <span>{c}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ))}

              {/* Metric comparison table */}
              <div>
                <h3 className="text-sm font-semibold text-gray-200 mb-3">Key Metric Definitions — How Sources Differ</h3>
                <div className="overflow-x-auto rounded-xl border border-gray-800">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-gray-800 bg-gray-800/60">
                        <th className="px-3 py-2.5 text-left font-medium text-gray-400 whitespace-nowrap">Metric</th>
                        <th className="px-3 py-2.5 text-left font-medium text-blue-400 whitespace-nowrap">
                          <DotBadge color="bg-blue-400" label="Screener.in" />
                        </th>
                        <th className="px-3 py-2.5 text-left font-medium text-violet-400 whitespace-nowrap">
                          <DotBadge color="bg-violet-400" label="yfinance" />
                        </th>
                        <th className="px-3 py-2.5 text-left font-medium text-amber-400 whitespace-nowrap">
                          <DotBadge color="bg-amber-400" label="Damodaran" />
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {DIFF_TABLE.map((row, i) => (
                        <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/20">
                          <td className="px-3 py-3 font-semibold text-gray-300 whitespace-nowrap align-top">
                            {row.metric}
                          </td>
                          <td className="px-3 py-3 text-gray-400 leading-relaxed align-top max-w-[200px]">
                            {row.screener.split('\n').map((l, j) => (
                              <span key={j}>{l}{j < row.screener.split('\n').length - 1 && <br />}</span>
                            ))}
                          </td>
                          <td className="px-3 py-3 text-gray-400 leading-relaxed align-top max-w-[220px]">
                            {row.yfinance.split('\n').map((l, j) => (
                              <span key={j} className={j === 1 ? 'text-amber-500/80' : ''}>{l}{j < row.yfinance.split('\n').length - 1 && <br />}</span>
                            ))}
                          </td>
                          <td className="px-3 py-3 text-gray-400 leading-relaxed align-top max-w-[200px]">
                            {row.damodaran.split('\n').map((l, j) => (
                              <span key={j}>{l}{j < row.damodaran.split('\n').length - 1 && <br />}</span>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Noisy field callout */}
              <div className="bg-gray-800/50 border border-gray-700 rounded-lg px-4 py-3 text-xs text-gray-400 leading-relaxed">
                <p className="font-semibold text-gray-300 mb-1">Why some Compare fields are marked <span className="text-gray-500 font-mono">†</span></p>
                Fields marked <span className="font-mono text-gray-500">†</span> in the comparison view (D/E and Promoter/Insider %) use fundamentally
                different definitions across sources — a large delta does <em>not</em> indicate a data error;
                it reflects a genuine methodological difference. These fields are excluded from the
                "Worst Δ" column to avoid false alarms.
              </div>

            </div>

            <div className="px-6 py-3 border-t border-gray-800 flex justify-end">
              <button
                onClick={() => setOpen(false)}
                className="px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
