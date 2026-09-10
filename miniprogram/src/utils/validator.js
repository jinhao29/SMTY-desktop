/** 表单校验 */
const PHONE_RE = /^1[3-9]\d{9}$/

export const isPhone = (v) => PHONE_RE.test(String(v || '').trim())

export const required = (v, label) => {
  if (v === undefined || v === null || String(v).trim() === '') {
    uni.showToast({ title: `${label}不能为空`, icon: 'none' })
    return false
  }
  return true
}

export const checkPhone = (v, label = '手机号', optional = true) => {
  const s = String(v || '').trim()
  if (!s) return optional ? true : (uni.showToast({ title: `${label}不能为空`, icon: 'none' }), false)
  if (!isPhone(s)) {
    uni.showToast({ title: `${label}格式不正确`, icon: 'none' })
    return false
  }
  return true
}

export const checkNumber = (v, label, min = null) => {
  const n = Number(v)
  if (v === '' || isNaN(n)) {
    uni.showToast({ title: `${label}必须是数字`, icon: 'none' })
    return false
  }
  if (min !== null && n < min) {
    uni.showToast({ title: `${label}不能小于 ${min}`, icon: 'none' })
    return false
  }
  return true
}
