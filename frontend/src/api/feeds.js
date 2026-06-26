import client from './client'

export const getFeeds = () => client.get('/feeds')
export const createFeed = (data) => client.post('/feeds', data)
export const suggestFeed = (domainCvId) => client.post('/feeds/suggest', { domain_cv_id: domainCvId })
export const searchApifyActors = (search) => client.get('/feeds/apify-actors', { params: { search } })
export const updateFeed = (id, data) => client.patch(`/feeds/${id}`, data)
export const toggleFeed = (id) => client.post(`/feeds/${id}/toggle`)
export const runFeed = (id) => client.post(`/feeds/${id}/run`)
export const deleteFeed = (id) => client.delete(`/feeds/${id}`)
export const getFeedsWithCounts = () => client.get('/feeds/with-counts')
export const getFeedPerformance = () => client.get('/feeds/performance')

export const getTargetCompanies = () => client.get('/companies')
export const addTargetCompany = (data) => client.post('/companies', data)
export const removeTargetCompany = (id) => client.delete(`/companies/${id}`)

export const triggerScan = () => client.post('/scanner/run')
export const getScannerStatus = () => client.get('/scanner/status')
