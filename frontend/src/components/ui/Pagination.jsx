import { useState, useEffect } from 'react'

// Reusable pagination control. Shows "Showing X-Y of N", Prev/Next, and up to 5
// page buttons with ellipsis. Renders nothing if there's only one page.
export default function Pagination({ currentPage, totalPages, totalItems, itemsPerPage = 10, onPageChange, label = 'items' }) {
  if (totalPages <= 1) return null
  const start = (currentPage - 1) * itemsPerPage + 1
  const end = Math.min(currentPage * itemsPerPage, totalItems)

  // Up to 5 page numbers centred on the current page.
  let pages = []
  if (totalPages <= 5) {
    pages = Array.from({ length: totalPages }, (_, i) => i + 1)
  } else {
    let lo = Math.max(1, currentPage - 2)
    let hi = Math.min(totalPages, lo + 4)
    lo = Math.max(1, hi - 4)
    pages = Array.from({ length: hi - lo + 1 }, (_, i) => lo + i)
  }

  const Btn = ({ disabled, active, onClick, children }) => (
    <button
      onClick={onClick} disabled={disabled}
      className={`min-w-[28px] h-7 px-2 text-xs rounded-md border transition-colors ${
        active ? 'bg-gray-800 text-white border-gray-800'
        : disabled ? 'text-gray-300 border-gray-100 cursor-not-allowed'
        : 'text-gray-600 border-gray-200 hover:bg-gray-50'
      }`}>
      {children}
    </button>
  )

  return (
    <div className="flex items-center justify-between gap-3 pt-3 mt-2 border-t border-gray-100 flex-wrap">
      <span className="text-xs text-gray-400">Showing {start}-{end} of {totalItems} {label}</span>
      <div className="flex items-center gap-1">
        <Btn disabled={currentPage <= 1} onClick={() => onPageChange(currentPage - 1)}>← Prev</Btn>
        {pages[0] > 1 && <span className="text-xs text-gray-300 px-1">…</span>}
        {pages.map((p) => (
          <Btn key={p} active={p === currentPage} onClick={() => onPageChange(p)}>{p}</Btn>
        ))}
        {pages[pages.length - 1] < totalPages && <span className="text-xs text-gray-300 px-1">…</span>}
        <Btn disabled={currentPage >= totalPages} onClick={() => onPageChange(currentPage + 1)}>Next →</Btn>
      </div>
    </div>
  )
}

// Convenience hook: paginate an in-memory array client-side.
export function usePagination(items, perPage = 10) {
  const [page, setPage] = useState(1)
  const list = items || []
  const total = list.length
  const totalPages = Math.max(1, Math.ceil(total / perPage))
  useEffect(() => { if (page > totalPages) setPage(1) }, [totalPages, page])
  const slice = list.slice((page - 1) * perPage, page * perPage)
  return { page, setPage, slice, total, totalPages, perPage }
}
