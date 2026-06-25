import client from './client'

export const getCareerAnalysis = () => client.get('/career/analysis')
export const triggerAnalysis = () => client.post('/career/analyse')
export const saveAnswer = (question_key, answer) => client.post('/career/questions', { question_key, answer })
export const getAnswers = () => client.get('/career/questions')
export const updateRoadmapItem = (id, is_completed) => client.patch(`/career/roadmap/${id}`, { is_completed })
export const getCommunityCareer = () => client.get('/career/community')
export const shareInsights = () => client.post('/career/share')
