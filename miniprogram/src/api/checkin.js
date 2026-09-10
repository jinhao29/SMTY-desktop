import { get, post } from '../utils/request'

export const checkin = (lessonId, studentIds, note = '') => post(`/api/v1/checkin/${lessonId}`, { student_ids: studentIds, note })
export const checkout = (lessonId, studentIds, note = '') => post(`/api/v1/checkout/${lessonId}`, { student_ids: studentIds, note })
export const history = (params = {}) => get('/api/v1/checkins', params)
export const pending = (date = '') => get('/api/v1/checkins/pending', { date })
export const todayList = () => get('/api/v1/checkins/today')
