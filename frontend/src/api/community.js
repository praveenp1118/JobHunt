import client from './client'

export const getCommunityInsights = (company, role, market, jdHash) =>
  client.get('/community/insights', {
    params: { company, role, ...(market ? { market } : {}), ...(jdHash ? { jd_hash: jdHash } : {}) },
  })

export const shareJobInsights = (jobId) => client.post(`/community/share/${jobId}`)

export const getMyContributions = () => client.get('/community/my-contributions')

export const updateCommunityPreferences = (enabled) =>
  client.patch('/community/preferences', { community_sharing_enabled: enabled })
