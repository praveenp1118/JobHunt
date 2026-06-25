import client from './client'

export const getLegalUrls = () => client.get('/settings/legal-urls')
export const recordConsent = () => client.post('/auth/consent')
