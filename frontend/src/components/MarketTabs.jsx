export default function MarketTabs({ markets, active, onChange, uploaded }) {
  return (
    <div className="flex gap-1 bg-gray-900 p-1 rounded-xl border border-gray-800">
      {markets.map((m) => (
        <button
          key={m.id}
          onClick={() => onChange(m.id)}
          className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all relative ${
            active === m.id
              ? 'bg-indigo-600 text-white shadow'
              : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
          }`}
        >
          {m.label}
          {uploaded.has(m.id) && (
            <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-emerald-400 rounded-full" />
          )}
        </button>
      ))}
    </div>
  )
}
