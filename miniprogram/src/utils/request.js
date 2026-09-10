/** 请求封装：自动携带 token、统一错误提示、401 跳登录 */

/**
 * 后端地址：优先取构建期环境变量 VITE_API_BASE_URL，其次取运行时 storage
 * （设置页可改，便于真机临时联调），最后回落本机开发地址。
 *
 * 部署公网后端时在 .env.production 里写：
 *   VITE_API_BASE_URL=https://your-api-domain.com
 * 微信要求：HTTPS、已 ICP 备案、域名需在小程序后台配置为 request 合法域名。
 */
const ENV_BASE_URL = (import.meta.env && import.meta.env.VITE_API_BASE_URL) || ''

/** 构建期默认地址（无环境变量时回落到本机开发地址） */
export const DEFAULT_BASE_URL = ENV_BASE_URL || 'http://127.0.0.1:8800'

export function getBaseUrl() {
  // 运行时覆盖优先（设置页写入，方便换服务器不用重新上传代码）
  const runtime = uni.getStorageSync('apiBaseUrl') || ''
  return (runtime || DEFAULT_BASE_URL).replace(/\/+$/, '')
}

/** 设置/清除运行时服务器地址（传空串 = 清除覆盖，回落构建期默认值） */
export function setBaseUrl(url) {
  if (url) {
    uni.setStorageSync('apiBaseUrl', String(url).trim())
  } else {
    uni.removeStorageSync('apiBaseUrl')
  }
}

/** 兼容既有 import { BASE_URL } 的调用点 */
export const BASE_URL = DEFAULT_BASE_URL

export function request({ url, method = 'GET', data = {}, loading = true }) {
  return new Promise((resolve, reject) => {
    const token = uni.getStorageSync('token') || ''
    if (loading) uni.showLoading({ title: '加载中', mask: true })
    uni.request({
      url: getBaseUrl() + url,
      method,
      data,
      header: {
        Authorization: 'Bearer ' + token,
        // 数据空间标识：后端按此路由到对应模式库
        'X-MP-Mode': uni.getStorageSync('mode') || 'shangmen',
      },
      success(res) {
        if (loading) uni.hideLoading()
        if (res.statusCode === 401) {
          uni.removeStorageSync('token')
          uni.reLaunch({ url: '/pages/login/login' })
          return reject(new Error('未登录'))
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          return resolve(res.data)
        }
        const msg = (res.data && res.data.detail) || `请求失败(${res.statusCode})`
        uni.showToast({ title: msg, icon: 'none' })
        reject(new Error(msg))
      },
      fail(err) {
        if (loading) uni.hideLoading()
        uni.showToast({ title: '网络异常，请检查后端服务', icon: 'none' })
        reject(err)
      },
    })
  })
}

export const get = (url, data) => request({ url, data })
export const post = (url, data) => request({ url, method: 'POST', data })
export const put = (url, data) => request({ url, method: 'PUT', data })
export const del = (url) => request({ url, method: 'DELETE' })
