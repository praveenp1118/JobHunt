import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { format } from 'date-fns'
import { getMyContributions } from '../../api/community'
import Spinner from '../../components/ui/Spinner'

export default function ContributionsPage() {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({ queryKey: ['my-contributions'], queryFn: getMyContributions })
  const rows = data?.data || []

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">🤝 My Community Contributions</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          You've contributed anonymised insights for <span className="font-medium">{rows.length}</span> job{rows.length === 1 ? '' : 's'}.
          Your CV is never shared.
        </p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : rows.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center">
          <p className="text-sm text-gray-400">No contributions yet.</p>
          <p className="text-xs text-gray-400 mt-1">
            Enable community sharing in Settings → Preferences, then apply to jobs to contribute.
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="border-b border-gray-100 bg-gray-50">
              <tr className="text-left text-[11px] text-gray-500">
                <th className="px-4 py-2 font-medium">Company</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Contributed</th>
                <th className="px-4 py-2 font-medium text-center">Contributors now</th>
                <th className="px-4 py-2 font-medium text-right">Insights</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {rows.map((r) => (
                <tr key={r.job_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{r.company}</td>
                  <td className="px-4 py-3 text-sm text-gray-600 truncate max-w-[220px]">{r.role}</td>
                  <td className="px-4 py-3 text-xs text-gray-400">{r.contributed_at ? format(new Date(r.contributed_at), 'MMM d, yyyy') : '—'}</td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-xs font-medium bg-indigo-50 text-indigo-600 rounded-full px-2 py-0.5">👥 {r.contributor_count}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => navigate(`/jobs?open=${r.job_id}`)}
                      className="text-xs text-emerald-600 hover:underline font-medium">View →</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
