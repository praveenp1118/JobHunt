import client from './client'

// Which billing provider is active (config-driven; flips Stripe↔Razorpay without a
// frontend redeploy). Cached for the session; falls back to 'stripe' on any error.
let _providerCache = null
export const getPaymentProvider = async () => {
  if (_providerCache) return _providerCache
  try {
    const { data } = await client.get('/billing/provider')
    _providerCache = data?.provider === 'razorpay' ? 'razorpay' : 'stripe'
  } catch { _providerCache = 'stripe' }
  return _providerCache
}

// Start a subscription. BOTH providers return { checkout_url } → the caller just does
// window.location.href = checkout_url.
export const createCheckoutSession = async (plan = 'pro') => {
  const provider = await getPaymentProvider()
  if (provider === 'razorpay') {
    return client.post('/billing/razorpay/create-subscription', { plan })
  }
  return client.post('/billing/create-checkout-session', {
    plan,
    success_url: `${window.location.origin}/billing/success`,
    cancel_url: `${window.location.origin}/settings#plan`,
  })
}

export const getSubscription = () =>
  client.get('/billing/subscription') // shared endpoint — reads provider-agnostic columns

export const cancelSubscription = async () => {
  const provider = await getPaymentProvider()
  return provider === 'razorpay'
    ? client.post('/billing/razorpay/cancel')
    : client.post('/billing/cancel')
}

// Success-page poll. Stripe verifies by session_id; Razorpay by subscription_id — the
// id comes from whatever the redirect appended (see SubscriptionSuccess).
export const verifySession = async (id) => {
  const provider = await getPaymentProvider()
  return provider === 'razorpay'
    ? client.get('/billing/razorpay/verify', { params: { subscription_id: id } })
    : client.get('/billing/verify-session', { params: { session_id: id } })
}
