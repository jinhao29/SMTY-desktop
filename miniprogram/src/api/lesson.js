import { get, post, put, del } from '../utils/request'

export const list = (params = {}) => get('/api/v1/lessons', params)
export const today = () => get('/api/v1/lessons/today')
export const week = (start, end) => get('/api/v1/lessons/week', { start, end })
export const detail = (id) => get(`/api/v1/lessons/${id}`)
export const create = (data) => post('/api/v1/lessons', data)
export const update = (id, data) => put(`/api/v1/lessons/${id}`, data)
export const remove = (id) => del(`/api/v1/lessons/${id}`)
