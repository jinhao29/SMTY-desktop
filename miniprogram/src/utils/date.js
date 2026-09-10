/** 日期工具：周课表 / 今日概览共用 */

export function pad(n) { return n < 10 ? '0' + n : '' + n }

export function fmt(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }

export function parseDate(s) {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function today() { return fmt(new Date()) }

/** 返回某日所在周的周一~周日日期数组 */
export function weekDates(dateStr) {
  const d = parseDate(dateStr)
  const day = d.getDay() === 0 ? 7 : d.getDay() // 周一为 1
  const monday = new Date(d)
  monday.setDate(d.getDate() - (day - 1))
  return Array.from({ length: 7 }, (_, i) => {
    const x = new Date(monday)
    x.setDate(monday.getDate() + i)
    return fmt(x)
  })
}

export function addDays(dateStr, n) {
  const d = parseDate(dateStr)
  d.setDate(d.getDate() + n)
  return fmt(d)
}

export const WEEK_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export function weekdayLabel(dateStr) {
  return WEEK_LABELS[(parseDate(dateStr).getDay() + 6) % 7]
}

/** MM-DD 短格式 */
export function shortDate(dateStr) { return dateStr.slice(5) }

/** YYYY-MM-DD HH:mm:ss（本地模式时间戳，与后端 now_str 格式一致） */
export function now() {
  const d = new Date()
  const time = pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds())
  return fmt(d) + ' ' + time
}
