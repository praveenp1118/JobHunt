import { useQuery } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import client from '../../api/client'
import Spinner from '../../components/ui/Spinner'
import Button from '../../components/ui/Button'
import { toast } from '../../store/toast'
import Pagination, { usePagination } from '../../components/ui/Pagination'

export default function ErrorLogTab() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['error-logs'],
    queryFn: () => client.get('/auth/admin/error-logs'),
    retry: false,
  })

  const errors = data?.data || []
  const pg = usePagination(errors, 10)

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-600">{errors.length} error{errors.length !== 1 ? 's' : ''} logged</p>
        <Button size="sm" variant="ghost" onClick={() => refetch()}>Refresh</Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : errors.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-200 p-12 text-center">
          <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center mx-auto mb-3">
            <svg className="w-6 h-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <p className="text-sm text-gray-500">No errors — everything is running smoothly</p>
        </div>
      ) : (
        <div className="space-y-2">
          {pg.slice.map((err) => (
            <div key={err.id} className={`bg-white rounded-xl border p-4 ${err.is_resolved ? 'border-gray-100 opacity-60' : 'border-red-100'}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-medium bg-red-50 text-red-600 px-2 py-0.5 rounded-full">
                      {err.action}
                    </span>
                    {err.retry_count > 0 && (
                      <span className="text-[10px] text-gray-400">{err.retry_count} retries</span>
                    )}
                    {err.is_resolved && (
                      <span className="text-[10px] text-emerald-600 font-medium">Resolved</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-700 truncate">{err.error_message}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {formatDistanceToNow(new Date(err.created_at), { addSuffix: true })}
                  </p>
                </div>
                {!err.is_resolved && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={async () => {
                      try {
                        await client.patch(`/admin/error-logs/${err.id}/resolve`)
                        refetch()
                      } catch (e) { console.error(e) }
                    }}
                  >
                    Mark resolved
                  </Button>
                )}
              </div>
            </div>
          ))}
          <Pagination currentPage={pg.page} totalPages={pg.totalPages} totalItems={pg.total} itemsPerPage={10} onPageChange={pg.setPage} label="errors" />
        </div>
      )}
    </div>
  )
}
