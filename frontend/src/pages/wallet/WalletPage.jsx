import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import client from '../../api/client'
import Spinner from '../../components/ui/Spinner'
import Button from '../../components/ui/Button'
import useAuthStore from '../../store/auth'

export default function WalletPage() {
  const { user } = useAuthStore()

  const { data, isLoading } = useQuery({
    queryKey: ['wallet'],
    queryFn: () => client.get('/wallet'),
    retry: false,
  })

  const wallet = data?.data || {}
  const transactions = wallet.transactions || []
  const balancePaise = wallet.balance_paise || 0
  const balanceRupees = (balancePaise / 100).toFixed(2)

  if (user?.plan === 'default') {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-gray-900">Wallet</h1>
          <p className="text-sm text-gray-500 mt-0.5">Credit balance for platform AI actions</p>
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center">
          <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
            </svg>
          </div>
          <h3 className="font-semibold text-gray-900 mb-2">You're on the Default plan</h3>
          <p className="text-sm text-gray-500 mb-2 max-w-sm mx-auto">
            You use your own Anthropic and Apify keys. Actions are billed directly to your accounts — no wallet needed.
          </p>
          <p className="text-xs text-gray-400">
            Switch to Wallet plan in Settings → Plan & Keys to use platform credits.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Wallet</h1>
        <p className="text-sm text-gray-500 mt-0.5">Credit balance for platform AI actions</p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : (
        <div className="space-y-5">
          {/* Balance card */}
          <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl p-6 text-white">
            <p className="text-sm text-slate-400 mb-1">Available balance</p>
            <p className="text-4xl font-bold">₹{balanceRupees}</p>
            <div className="flex items-center justify-between mt-4">
              <p className="text-xs text-slate-500">Wallet plan · Pay per action</p>
              <Button
                className="bg-emerald-500 hover:bg-emerald-600 text-white border-transparent"
                size="sm"
                onClick={() => alert('Top up via Razorpay — coming in V2')}
              >
                + Top up
              </Button>
            </div>
          </div>

          {/* Action pricing reference */}
          <div className="bg-white rounded-2xl border border-gray-200 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Action pricing</h3>
            <div className="grid grid-cols-2 gap-2">
              {[
                { action: 'Parse JD', price: '₹1' },
                { action: 'S1 base score', price: '₹1' },
                { action: 'S2 + S3 score', price: '₹1.50' },
                { action: 'Domain CV generate', price: '₹3' },
                { action: 'Tailor + CL + email', price: '₹2.50' },
                { action: 'Interview prep', price: '₹2' },
                { action: 'Follow-up draft', price: '₹0.50' },
                { action: 'Gmail classify (per email)', price: '₹0.10' },
                { action: 'Apify job found', price: '₹0.25' },
              ].map(({ action, price }) => (
                <div key={action} className="flex items-center justify-between py-1.5 border-b border-gray-50">
                  <span className="text-xs text-gray-600">{action}</span>
                  <span className="text-xs font-semibold text-gray-900">{price}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Transaction history */}
          <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900">Transaction history</h3>
            </div>
            {transactions.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-sm text-gray-400">No transactions yet</p>
              </div>
            ) : (
              <table className="w-full">
                <thead className="border-b border-gray-50">
                  <tr>
                    {['Date', 'Action', 'Amount', 'Balance'].map((h) => (
                      <th key={h} className="px-4 py-2 text-left text-xs font-medium text-gray-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {transactions.map((tx) => (
                    <tr key={tx.id}>
                      <td className="px-4 py-2.5 text-xs text-gray-400">
                        {tx.created_at ? format(new Date(tx.created_at), 'MMM d HH:mm') : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-sm text-gray-700">{tx.description}</td>
                      <td className={`px-4 py-2.5 text-sm font-medium ${tx.amount_paise >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                        {tx.amount_paise >= 0 ? '+' : ''}₹{(tx.amount_paise / 100).toFixed(2)}
                      </td>
                      <td className="px-4 py-2.5 text-sm text-gray-700">
                        ₹{(tx.balance_after_paise / 100).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
