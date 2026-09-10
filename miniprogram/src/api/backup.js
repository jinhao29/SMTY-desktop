import { get, post } from '../utils/request'

export const exportData = () => get('/api/v1/backup/export')
export const importData = (payload) => post('/api/v1/backup/import', payload)
