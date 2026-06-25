import client from './client'

export const getUsageLogs = (provider = 'all', category = 'all', days = 30) =>
  client.get('/usage/logs', { params: { provider, category, days } })

export const exportUsageCSV = (days = 30) =>
  client.get('/usage/export', { params: { days }, responseType: 'blob' })
