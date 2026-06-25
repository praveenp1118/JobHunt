import client from './client'

export const getCVTemplate = () => client.get('/templates/cv')
export const updateCVTemplate = (data) => client.put('/templates/cv', data)
export const getFonts = () => client.get('/templates/cv/fonts')
export const getDomainOverride = (domainCvId) => client.get(`/templates/domain/${domainCvId}`)
export const updateDomainOverride = (domainCvId, data) => client.put(`/templates/domain/${domainCvId}`, data)
export const deleteDomainOverride = (domainCvId) => client.delete(`/templates/domain/${domainCvId}`)
