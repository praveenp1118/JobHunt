import client from './client'

export const getAlertActivity = (days = 7) =>
  client.get('/activity/alerts', { params: { days } })

export const getSystemActivity = (days = 7) =>
  client.get('/activity/system', { params: { days } })

// Manual "run now" triggers
export const pollGmailNow = () => client.post('/gmail/poll')
export const runScanNow = () => client.post('/scanner/run')
