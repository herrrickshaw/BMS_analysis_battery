import { useRef, useState } from 'react'

export default function UploadPanel({ onUpload, loading, marketLabel }) {
  const inputRef = useRef()
  const [dragging, setDragging] = useState(false)

  const handle = (file) => { if (file) onUpload(file) }

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Upload Data
      </h3>
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handle(e.dataTransfer.files[0]) }}
        className={`border-2 border-dashed rounded-lg p-5 text-center cursor-pointer transition-colors ${
          dragging
            ? 'border-indigo-500 bg-indigo-950/20'
            : 'border-gray-700 hover:border-gray-600'
        }`}
      >
        <div className="text-2xl font-mono text-gray-600 mb-1">[+]</div>
        <p className="text-xs text-gray-400">
          Drop CSV / Excel or <span className="text-indigo-400">click to browse</span>
        </p>
        <p className="text-xs text-gray-600 mt-1">for {marketLabel}</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={(e) => handle(e.target.files[0])}
      />
      {loading && (
        <p className="text-xs text-indigo-400 mt-2 text-center animate-pulse">
          Processing...
        </p>
      )}
    </div>
  )
}
