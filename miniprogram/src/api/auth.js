import { get, post } from '../utils/request'

export const login = (phone, password) => post('/api/v1/auth/login', { phone, password })
export const logout = () => post('/api/v1/auth/logout')
export const me = () => get('/api/v1/auth/me')
