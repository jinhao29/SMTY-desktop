import { get, post, put, del } from '../utils/request'

export const list = (params = {}) => get('/api/v1/packages', params)
export const stats = () => get('/api/v1/packages/stats')
export const detail = (id) => get(`/api/v1/packages/${id}`)
export const create = (data) => post('/api/v1/packages', data)
export const update = (id, data) => put(`/api/v1/packages/${id}`, data)
export const remove = (id) => del(`/api/v1/packages/${id}`)
