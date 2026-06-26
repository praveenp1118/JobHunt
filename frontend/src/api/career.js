import client from './client'

export const getCareerAnalysis = (params = {}) => client.get('/career/analysis', { params })
export const triggerAnalysis = (params = {}) => client.post('/career/analyse', null, { params })
export const saveAnswer = (question_key, answer) => client.post('/career/questions', { question_key, answer })
export const getAnswers = () => client.get('/career/questions')
export const updateRoadmapItem = (id, is_completed) => client.patch(`/career/roadmap/${id}`, { is_completed })
export const getCommunityCareer = () => client.get('/career/community')
export const shareInsights = () => client.post('/career/share')
