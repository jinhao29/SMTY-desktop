import { get, post, put, del } from '../utils/request'

export const list = (params = {}) => get('/api/v1/coaches', params)
export const detail = (id) => get(`/api/v1/coaches/${id}`)
export const create = (data) => post('/api/v1/coaches', data)
export const update = (id, data) => put(`/api/v1/coaches/${id}`, data)
export const remove = (id) => del(`/api/v1/coaches/${id}`)
export const schedule = (id, start = '', end = '') => get(`/api/v1/coaches/${id}/schedule`, { start, end })
export const payout = (id) => get(`/api/v1/coaches/${id}/payout`)
