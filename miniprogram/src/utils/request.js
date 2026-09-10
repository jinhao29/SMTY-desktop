/** 请求封装：自动携带 token、统一错误提示、401 跳登录 */

export const BASE_URL = 'http://127.0.0.1:8800' // 部署时替换为 HTTPS 域名

export function request({ url, method = 'GET', data = {}, loading = true }) {
  return new Promise((resolve, reject) => {
    const token = uni.getStorageSync('token') || ''
    if (loading) uni.showLoading({ title: '加载中', mask: true })
    uni.request({
      url: BASE_URL + url,
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
