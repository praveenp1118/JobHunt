import client from './client'

// Master CV
export const getMasterCV = () =>
  client.get('/cvs/master')

export const saveMasterCVText = (contentMd, changeSummary) =>
  client.post('/cvs/master/text', { content_md: contentMd, change_summary: changeSummary })

export const uploadMasterCVFile = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return client.post('/cvs/master/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const updateMasterCV = (contentMd, changeSummary) =>
  client.put('/cvs/master', { content_md: contentMd, change_summary: changeSummary })

export const getMasterCVVersions = () =>
  client.get('/cvs/master/versions')

export const rollbackMasterCV = (version) =>
  client.post(`/cvs/master/rollback/${version}`)

// Domain CVs
export const getDomainCVs = () =>
  client.get('/cvs/domains')

export const getDomainCV = (id) =>
  client.get(`/cvs/domains/${id}`)

export const generateDomainChangelog = (industryId, functionId, countryCode) =>
  client.post('/cvs/domains/generate-changelog', {
    industry_id: industryId,
    function_id: functionId,
    country_code: countryCode,
  })

export const getDomainChangelog = (domainCvId) =>
  client.get(`/cvs/domains/${domainCvId}/changelog`)

export const approveChange = (domainCvId, changeId) =>
  client.post(`/cvs/domains/${domainCvId}/changelog/${changeId}/approve`)

export const rejectChange = (domainCvId, changeId) =>
  client.post(`/cvs/domains/${domainCvId}/changelog/${changeId}/reject`)

export const editChange = (domainCvId, changeId, finalText) =>
  client.put(`/cvs/domains/${domainCvId}/changelog/${changeId}/edit`, { final_text: finalText })

export const bulkChangeAction = (domainCvId, action) =>
  client.post(`/cvs/domains/${domainCvId}/changelog/bulk`, { action })

export const applyDomainCV = (domainCvId) =>
  client.post(`/cvs/domains/${domainCvId}/apply`)
