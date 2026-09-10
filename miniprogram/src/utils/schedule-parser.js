/**
 * 课表文本解析：每行一节课，批量导入用。
 * 支持格式（宽松匹配）：
 *   周一 15:00-16:00 陈小明 私教 雅居乐花园
 *   周二 17:00 林小雨、黄浩然 小班课 大学城体育中心
 *   9/12 10:00-11:30 王一
 *   9月14日 9点 陈小明
 * ponytail: 地点取残留文本第一个词，启发式，解析结果在预览中可见可删。
 */

const WEEK_MAP = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 0, 天: 0 }

/** "HH:MM" + 分钟 → "HH:MM" */
function plusMinutes(hhmm, mins) {
  const [h, m] = hhmm.split(':').map(Number)
  const t = (h * 60 + m + mins) % 1440
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`
}

/** 星期几(0=日) → 距 weekStartISO(周一) 的 ISO 日期 */
function weekdayToDate(weekday, weekStartISO) {
  if (!weekStartISO) return null
  const base = new Date(weekStartISO + 'T00:00:00')
  const offset = weekday === 0 ? 6 : weekday - 1
  base.setDate(base.getDate() + offset)
  // 本地时区手动格式化；toISOString 会按 UTC 回退导致日期差一天
  const p = (n) => String(n).padStart(2, '0')
  return `${base.getFullYear()}-${p(base.getMonth() + 1)}-${p(base.getDate())}`
}

/**
 * @param {string} text 多行文本
 * @param {Array<{id:Number,name:String}>} students 学员名单（用于姓名匹配）
 * @param {string} weekStartISO 「周X」归属的周一日期，如 2026-09-14
 * @returns {{ items: Array, errors: Array }}
 */
export function parseSchedule(text, students = [], weekStartISO = '') {
  const items = []
  const errors = []
  // 长名优先匹配，防止「陈小明」被短名「陈小」截胡
  const sorted = [...students].sort((a, b) => b.name.length - a.name.length)
  const now = new Date()
  const y = now.getFullYear()
  const ym = now.getMonth() + 1

  for (const line of text.split(/\n+/).map(l => l.trim()).filter(Boolean)) {
    let rest = ' ' + line + ' '
    let date = null

    // 绝对日期：M月D日 / M/D / M-D
    let m = rest.match(/(\d{1,2})\s*[月/·]\s*(\d{1,2})\s*[日号]?/)
    if (m) {
      const mm = +m[1], dd = +m[2]
      if (mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31) {
        // 已过的月份视为明年（年底排下学期课表）
        const yy = mm < ym ? y + 1 : y
        date = `${yy}-${String(mm).padStart(2, '0')}-${String(dd).padStart(2, '0')}`
        rest = rest.replace(m[0], ' ')
      }
    }
    // 星期：周X / 星期X
    if (!date) {
      m = rest.match(/(?:周|星期)\s*([一二三四五六日天])/)
      if (m) {
        date = weekdayToDate(WEEK_MAP[m[1]], weekStartISO)
        rest = rest.replace(m[0], ' ')
      }
    }
    if (!date) { errors.push({ line, reason: '缺少日期（周X 或 M/D）' }); continue }

    // 时间段：HH:MM-HH:MM（冒号/点、各种连接符）
    m = rest.match(/(\d{1,2})\s*[:：点]\s*(\d{2})?\s*[-~—–至到]\s*(\d{1,2})\s*[:：点]\s*(\d{2})?/)
    let start = '', end = ''
    if (m) {
      start = `${m[1].padStart(2, '0')}:${m[2] || '00'}`
      end = `${m[3].padStart(2, '0')}:${m[4] || '00'}`
      rest = rest.replace(m[0], ' ')
    } else {
      // 只有开始时间 → 默认 1 小时
      m = rest.match(/(\d{1,2})\s*[:：点]\s*(\d{2})?/)
      if (m) {
        start = `${m[1].padStart(2, '0')}:${m[2] || '00'}`
        end = plusMinutes(start, 60)
        rest = rest.replace(m[0], ' ')
      } else { errors.push({ line, reason: '缺少时间（HH:MM）' }); continue }
    }

    // 课程类型（吞掉整个词，防止「小班课」匹配后残留「课」混进地点）
    let type = 'private'
    m = rest.match(/小班课?|团课?|私教|一对一|一对多/)
    if (m) {
      const kw = m[0]
      if (kw.includes('小班')) type = 'small_group'
      else if (kw.includes('团')) type = 'group'
      rest = rest.replace(m[0], ' ')
    }

    // 学员匹配（长名优先，命中即从文本中移除）
    const student_ids = []
    for (const s of sorted) {
      if (rest.includes(s.name)) {
        student_ids.push(s.id)
        rest = rest.split(s.name).join(' ')
      }
    }

    // 地点：残留文本里第一段 ≥2 字的词（学员名/时间/类型已移除）
    const leftover = rest.replace(/[，,、。;；|]/g, ' ').trim()
    const location = leftover ? leftover.split(/\s+/)[0] : ''

    items.push({
      date, start_time: start, end_time: end, type,
      student_ids, location, raw: line,
      missing: student_ids.length === 0,
    })
  }
  return { items, errors }
}
