import { Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import Sidebar from './Sidebar'
import { getJobs } from '../../api/jobs'

export default function AppLayout() {
  const { data: hitlData } = useQuery({
    queryKey: ['hitl-count'],
    queryFn: () => getJobs({ needs_hitl: true, limit: 1 }),
    refetchInterval: 60000,
    retry: false,
  })

  const hitlCount = hitlData?.data?.total_count || 0

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <Sidebar hitlCount={hitlCount} />
      <main className="flex-1 overflow-y-auto min-w-0">
        <Outlet />
      </main>
    </div>
  )
}
