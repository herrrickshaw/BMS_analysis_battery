import DisclaimerModal from './DisclaimerModal'

export default function Header() {
  return (
    <header className="bg-gray-900 border-b border-gray-800 px-6 py-4">
      <div className="max-w-screen-2xl mx-auto flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-white tracking-tight">Stock Screener</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Darvas Box &nbsp;·&nbsp; Piotroski F-Score &nbsp;·&nbsp; Coffee Can
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-xs text-gray-600">
            <span className="w-2 h-2 rounded-full bg-blue-400 inline-block" title="Screener.in" />
            <span>Screener.in</span>
            <span className="w-2 h-2 rounded-full bg-violet-400 inline-block ml-1" title="yfinance" />
            <span>yfinance</span>
            <span className="w-2 h-2 rounded-full bg-amber-400 inline-block ml-1" title="Damodaran" />
            <span>Damodaran</span>
          </div>
          <DisclaimerModal />
        </div>
      </div>
    </header>
  )
}
