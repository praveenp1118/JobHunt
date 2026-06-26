import client from './client'

export const getScoringConfig = () => client.get('/scoring/config')
export const updateScoringConfig = (data) => client.patch('/scoring/config', data)
export const getScoringEstimate = () => client.get('/scoring/estimate')
export const recomputeMasterEssence = () => client.post('/cvs/master/recompute-essence')
