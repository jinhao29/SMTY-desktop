/**
 * API 统一出口（双模式分流）。
 *
 * authMode = 'local'（默认）：无服务器/无数据库时使用，数据存本机 storage，
 *   业务逻辑在 utils/local-store.js 端上复刻，与后端口径一致。
 * authMode = 'server'：走 HTTP 后端。
 *
 * 两种模式的备份 JSON 格式一致，可在设置-数据管理里互导。
 */
import * as serverAuth from './auth'
import * as serverStudent from './student'
import * as serverCoach from './coach'
import * as serverLesson from './lesson'
import * as serverCheckin from './checkin'
import * as serverPackage from './package'
import * as serverBackup from './backup'
import {
  studentStore, coachStore, lessonStore, checkinStore, packageStore,
  exportBackup, importBackup,
} from '../utils/local-store'

export const isLocalMode = () => (uni.getStorageSync('authMode') || 'local') === 'local'

/** 本地 store 的 __error 转成 toast + reject，与 request.js 行为一致 */
function run(promiseOrResult) {
  return Promise.resolve(promiseOrResult).then(res => {
    if (res && res.__error) {
      uni.showToast({ title: res.__error, icon: 'none' })
      throw new Error(res.__error)
    }
    return res
  })
}

function pick(serverFn, localFn) {
  return (...args) => (isLocalMode() ? run(localFn(...args)) : serverFn(...args))
}

function pickModule(serverMod, localMod) {
  const out = {}
  Object.keys(serverMod).forEach(fn => {
    if (typeof serverMod[fn] === 'function' && typeof localMod[fn] === 'function') {
      out[fn] = pick(serverMod[fn], localMod[fn])
    }
  })
  return out
}

// ---------------- auth ----------------

export const authApi = {
  login(...args) {
    if (isLocalMode()) {
      // 本地模式无需校验：任意账号直接进入（数据存本机）
      return run(Promise.resolve({
        token: 'local',
        user: { id: 0, phone: args[0] || '', name: '本地用户', role: 'local' },
      }))
    }
    return serverAuth.login(...args)
  },
  logout(...args) {
    if (isLocalMode()) return run(Promise.resolve({ ok: true }))
    return serverAuth.logout(...args)
  },
  me(...args) {
    if (isLocalMode()) {
      const user = uni.getStorageSync('user')
      return run(Promise.resolve(user || { id: 0, name: '本地用户', role: 'local' }))
    }
    return serverAuth.me(...args)
  },
}

// ---------------- 业务模块 ----------------

export const studentApi = pickModule(serverStudent, studentStore)
export const coachApi = pickModule(serverCoach, coachStore)
export const lessonApi = pickModule(serverLesson, lessonStore)
export const checkinApi = pickModule(serverCheckin, checkinStore)
export const packageApi = pickModule(serverPackage, packageStore)

// ---------------- backup（本地导出需带 mode） ----------------

export const backupApi = {
  exportData(...args) {
    if (isLocalMode()) {
      const mode = uni.getStorageSync('mode') || 'shangmen'
      return run(Promise.resolve(exportBackup(mode)))
    }
    return serverBackup.exportData(...args)
  },
  importData(...args) {
    if (isLocalMode()) {
      const mode = uni.getStorageSync('mode') || 'shangmen'
      return run(Promise.resolve(importBackup(args[0], mode)))
    }
    return serverBackup.importData(...args)
  },
}
