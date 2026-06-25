import client from './client'

export const getJobs = (params = {}) =>
  client.get('/jobs', { params })

export const getJobStats = () =>
  client.get('/jobs/stats')

export const getJob = (id) =>
  client.get(`/jobs/${id}`)

export const parseJobFromText = (rawText, scoreImmediately = true) =>
  client.post('/jobs/parse/text', { raw_text: rawText, score_immediately: scoreImmediately })

export const parseJobFromURL = (url) =>
  client.post('/jobs/parse/url', { url })

export const confirmJob = (tempId, data) =>
  client.post(`/jobs/confirm/${tempId}`, data)

export const updateJobStatus = (id, status, notes) =>
  client.patch(`/jobs/${id}/status`, { status, notes })

// Queue a background fetch of the full JD (from portal_url) + re-score a partial-JD job.
export const fetchJobJd = (id) =>
  client.post(`/jobs/${id}/fetch-jd`)

// User pastes the full JD (read on LinkedIn/etc) → save + queue S1/S1d scoring.
export const addFullJd = (id, jd_text) =>
  client.post(`/jobs/${id}/add-full-jd`, { jd_text })

export const updateJob = (id, data) =>
  client.patch(`/jobs/${id}`, data)

export const deleteJob = (id) =>
  client.delete(`/jobs/${id}?confirm=true`)

export const getJobEmails = (id) =>
  client.get(`/jobs/${id}/emails`)

export const scoreJobS1 = (id) =>
  client.post(`/jobs/${id}/score-s1`)

// Tailor
export const getJdHighlights = (jobId, domainCvId) =>
  client.post('/tailor/jd-highlights', { job_id: jobId, domain_cv_id: domainCvId })

export const generateTailor = (jobId, domainCvId) =>
  client.post('/tailor/generate', { job_id: jobId, domain_cv_id: domainCvId })

export const getTailorChangelog = (tailoredCvId) =>
  client.get(`/tailor/${tailoredCvId}/changelog`)

export const approveChange = (tailoredCvId, changeId) =>
  client.post(`/tailor/${tailoredCvId}/changelog/${changeId}/approve`)

export const rejectChange = (tailoredCvId, changeId) =>
  client.post(`/tailor/${tailoredCvId}/changelog/${changeId}/reject`)

export const editChange = (tailoredCvId, changeId, finalText) =>
  client.put(`/tailor/${tailoredCvId}/changelog/${changeId}/edit`, { final_text: finalText })

export const applyTailor = (tailoredCvId) =>
  client.post(`/tailor/${tailoredCvId}/apply`)

export const trimTailor = (tailoredCvId) =>
  client.post(`/tailor/${tailoredCvId}/trim`)

export const regenerateCL = (tailoredCvId, excludeTemplate) =>
  client.post(`/tailor/${tailoredCvId}/regenerate-cl`, { exclude_template: excludeTemplate })

export const draftFollowUp = (jobId, context) =>
  client.post(`/tailor/followup/${jobId}`, { context })

// Gmail
export const sendApplication = (data) =>
  client.post('/gmail/send-application', data)

export const sendReply = (data) =>
  client.post('/gmail/reply', data)

export const pollGmail = (sinceHours = 24) =>
  client.post('/gmail/poll', null, { params: { since_hours: sinceHours } })

// Feeds
export const getFeeds = () => client.get('/feeds')
export const triggerScan = () => client.post('/scanner/run')
export const getScannerStatus = () => client.get('/scanner/status')
