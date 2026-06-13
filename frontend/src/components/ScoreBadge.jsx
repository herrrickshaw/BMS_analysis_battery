/**
 * Scan-type-aware score badge component.
 *
 * Darvas       BUY (≥7): green   WATCH (4-6): amber   AVOID (<4): red
 * Piotroski    BUY (8-9): dark-green   WATCH (6-7): amber   AVOID (≤5): red
 * Coffee Can   score=1 → green checkmark   score=0 → red cross
 */

const SIGNAL_STYLE = {
  BUY:      { badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-700', bar: 'bg-emerald-500', label: 'BUY' },
  BUY_DARK: { badge: 'bg-emerald-700/50 text-emerald-100 border-emerald-500', bar: 'bg-emerald-600', label: 'BUY ★' },
  WATCH:    { badge: 'bg-amber-500/20   text-amber-300   border-amber-700',   bar: 'bg-amber-500',   label: 'WATCH' },
  AVOID:    { badge: 'bg-red-500/20     text-red-300     border-red-700',     bar: 'bg-red-500',     label: 'AVOID' },
}

export default function ScoreBadge({ score, maxScore, signal, scanType }) {
  // Coffee Can: checkmark or cross — no progress bar
  if (scanType === 'coffee_can') {
    const passed = score >= 1
    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-bold tracking-wide ${
          passed
            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-700'
            : 'bg-red-500/20     text-red-300     border-red-700'
        }`}
      >
        {passed ? '✓ Pass' : '✗ Fail'}
      </span>
    )
  }

  // Piotroski 8-9: dark green; otherwise use signal
  const styleKey = scanType === 'piotroski' && score >= 8 ? 'BUY_DARK' : signal
  const style = SIGNAL_STYLE[styleKey] || SIGNAL_STYLE.AVOID
  const pct   = maxScore > 0 ? Math.min(100, (score / maxScore) * 100) : 0

  return (
    <div className="flex items-center gap-2">
      <span className={`px-1.5 py-0.5 rounded border text-xs font-bold whitespace-nowrap ${style.badge}`}>
        {style.label}
      </span>
      <div className="flex items-center gap-1">
        <div className="w-14 h-1.5 bg-gray-700 rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${style.bar}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="text-xs text-gray-500 font-mono">{score}/{maxScore}</span>
      </div>
    </div>
  )
}
