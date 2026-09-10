import { get, post, put, del } from '../utils/request'

export const list = (params = {}) => get('/api/v1/students', params)
export const detail = (id) => get(`/api/v1/students/${id}`)
export const create = (data) => post('/api/v1/students', data)
export const update = (id, data) => put(`/api/v1/students/${id}`, data)
export const remove = (id) => del(`/api/v1/students/${id}`)
export const lessons = (id) => get(`/api/v1/students/${id}/lessons`)
export const checkins = (id, date = '') => get(`/api/v1/students/${id}/checkins`, { date })
