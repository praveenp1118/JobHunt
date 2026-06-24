import client from './client'

// Stripe checkout for JobHunt Pro. The backend appends ?session_id={CHECKOUT_SESSION_ID}
// to success_url, which the SubscriptionSuccess page reads to verify the session.
export const createCheckoutSession = (plan = 'pro') =>
  client.post('/billing/create-checkout-session', {
    plan,
    success_url: `${window.location.origin}/billing/success`,
    cancel_url: `${window.location.origin}/settings#plan`,
  })

export const getSubscription = () =>
  client.get('/billing/subscription')

export const cancelSubscription = () =>
  client.post('/billing/cancel')

export const verifySession = (sessionId) =>
  client.get('/billing/verify-session', { params: { session_id: sessionId } })
