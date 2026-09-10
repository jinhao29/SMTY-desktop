/**
 * 本地数据仓库（无服务器模式）。
 *
 * 全部业务数据存 uni storage，接口签名与 server API 完全一致，
 * 业务口径与后端 database.py 保持对齐：
 * - 学员剩余课时 = 有效课时包 remaining 之和
 * - 签到扣课时：最早到期包优先，扣完标记 exhausted
 * - 费用：应收=Σ总课时×单价；实收=paid_amount(-1 视同付清)；待收=应收-实收
 * - 备份 JSON 与服务器导出格式一致（mode/export_version + 五张表），可互导
 */
import { today, now } from './date'

// 数据空间按模式隔离：key 带模式后缀（与后端分库、PC 端 mode_guard 同思路）
const curMode = () => uni.getStorageSync('mode') || 'shangmen'
const K = {
  get seq() { return `local_seq_${curMode()}` },
  get students() { return `local_students_${curMode()}` },
  get coaches() { return `local_coaches_${curMode()}` },
  get lessons() { return `local_lessons_${curMode()}` },
  get packages() { return `local_packages_${curMode()}` },
  get checkins() { return `local_checkins_${curMode()}` },
}

const read = (key, fallback = []) => {
  const v = uni.getStorageSync(key)
  return Array.isArray(v) ? v : fallback
}
const write = (key, arr) => uni.setStorageSync(key, arr)

function nextId() {
  const n = (uni.getStorageSync(K.seq) || 0) + 1
  uni.setStorageSync(K.seq, n)
  return n
}

const stamp = () => now()

function publicList(table) {
  return read(K[table]).filter(r => !r.deleted)
}

function persist(table, rows) {
  write(K[table], rows)
}

/** 全库行（含软删除），备份用 */
function allRows(table) {
  return read(K[table])
}

function recalcRemaining(studentId) {
  const rows = read(K.packages)
  const total = rows
    .filter(p => p.student_id === studentId && !p.deleted && p.status === 'active')
    .reduce((s, p) => s + (p.remaining_lessons || 0), 0)
  const students = read(K.students).map(s =>
    s.id === studentId ? { ...s, remaining_lessons: total, updated_at: stamp() } : s)
  write(K.students, students)
}

function refreshExpired() {
  const t = today()
  let changed = false
  const rows = read(K.packages).map(p => {
    if (!p.deleted && p.status === 'active' && p.expire_date && p.expire_date < t && p.remaining_lessons > 0) {
      changed = true
      return { ...p, status: 'expired', updated_at: stamp() }
    }
    return p
  })
  if (changed) write(K.packages, rows)
}

function feeStats() {
  refreshExpired()
  const rows = publicList('packages')
  const total = rows.reduce((s, p) => s + p.total_lessons, 0)
  const remaining = rows.reduce((s, p) => s + p.remaining_lessons, 0)
  let receivable = 0
  let received = 0
  rows.forEach(p => {
    const unit = p.total_lessons ? p.price / p.total_lessons : 0
    receivable += p.total_lessons * unit
    received += p.paid_amount === -1 ? p.price : (p.paid_amount || 0)
  })
  return {
    total_lessons: total,
    consumed_lessons: total - remaining,
    remaining_lessons: remaining,
    student_count: new Set(rows.map(p => p.student_id)).size,
    total_receivable: Math.round(receivable * 100) / 100,
    total_received: Math.round(received * 100) / 100,
    total_pending: Math.round((receivable - received) * 100) / 100,
  }
}

function withStudentNames(rows) {
  const names = {}
  read(K.students).forEach(s => { names[s.id] = s.name })
  return rows.map(r => ({ ...r, student_name: names[r.student_id] || `#${r.student_id}` }))
}

// ---------------- students ----------------

export const studentStore = {
  list({ keyword = '', status = '', class_group = '', page_size = 50, page = 1 } = {}) {
    let rows = publicList('students')
    if (keyword) {
      const k = keyword.toLowerCase()
      rows = rows.filter(s => [s.name, s.phone, s.parent_phone].some(v => (v || '').toLowerCase().includes(k)))
    }
    if (status) rows = rows.filter(s => s.status === status)
    if (class_group) rows = rows.filter(s => s.class_group === class_group)
    return { total: rows.length, page, list: rows.slice(0, page_size) }
  },
  detail(id) {
    return publicList('students').find(s => s.id === id) || null
  },
  create(data) {
    const rows = read(K.students)
    const id = nextId()
    rows.push({ id, remaining_lessons: 0, status: 'active', ...data, created_at: stamp(), updated_at: stamp(), deleted: 0 })
    write(K.students, rows)
    return { id }
  },
  update(id, data) {
    write(K.students, read(K.students).map(s => (s.id === id ? { ...s, ...data, updated_at: stamp() } : s)))
    return { ok: true }
  },
  remove(id) {
    write(K.students, read(K.students).map(s => (s.id === id ? { ...s, deleted: 1, updated_at: stamp() } : s)))
    return { ok: true }
  },
  lessons(id) {
    const sids = [id]
    const inLesson = l => (l.student_ids || []).some(x => sids.includes(x))
    return {
      lessons: publicList('lessons').filter(inLesson),
      packages: publicList('packages').filter(p => p.student_id === id)
        .sort((a, b) => (b.purchase_date || '').localeCompare(a.purchase_date || '')),
      checkins: read(K.checkins).filter(c => c.student_id === id)
        .sort((a, b) => b.timestamp.localeCompare(a.timestamp)),
    }
  },
  checkins(id, date = '') {
    let rows = read(K.checkins).filter(c => c.student_id === id)
    if (date) rows = rows.filter(c => c.timestamp.startsWith(date))
    return { list: rows.sort((a, b) => b.timestamp.localeCompare(a.timestamp)) }
  },
}

// ---------------- coaches ----------------

const ROLE_LABELS = { fulltime: '全职', parttime: '兼职', partner_level1: '一级合伙人', partner_level2: '二级合伙人' }

export const coachStore = {
  list({ keyword = '', role = '', page_size = 50 } = {}) {
    let rows = publicList('coaches')
    if (keyword) {
      const k = keyword.toLowerCase()
      rows = rows.filter(c => [c.name, c.phone].some(v => (v || '').toLowerCase().includes(k)))
    }
    if (role) rows = rows.filter(c => c.role === role)
    const stats = { total: rows.length }
    Object.keys(ROLE_LABELS).forEach(k => { stats[k] = publicList('coaches').filter(c => c.role === k).length })
    stats.total = publicList('coaches').length
    return { total: rows.length, page: 1, stats, list: rows.slice(0, page_size) }
  },
  detail(id) {
    return publicList('coaches').find(c => c.id === id) || null
  },
  create(data) {
    const rows = read(K.coaches)
    const id = nextId()
    rows.push({ id, superior_id: null, status: 'active', salary_mode: 'per_lesson',
      base_salary: 0, lesson_rate: 0, commission_rate: 0, specialties: [],
      ...data, created_at: stamp(), updated_at: stamp(), deleted: 0 })
    write(K.coaches, rows)
    return { id }
  },
  update(id, data) {
    write(K.coaches, read(K.coaches).map(c => (c.id === id ? { ...c, ...data, updated_at: stamp() } : c)))
    return { ok: true }
  },
  remove(id) {
    write(K.coaches, read(K.coaches).map(c => (c.id === id ? { ...c, deleted: 1, updated_at: stamp() } : c)))
    return { ok: true }
  },
  schedule(id, start = '', end = '') {
    let rows = publicList('lessons').filter(l => l.coach_id === id)
    if (start && end) rows = rows.filter(l => l.date >= start && l.date <= end)
    rows.sort((a, b) => (a.date + a.start_time).localeCompare(b.date + b.start_time))
    return { list: rows }
  },
  payout(id) {
    const coach = this.detail(id)
    if (!coach) return null
    const rows = publicList('lessons').filter(l => l.coach_id === id)
    const signed = rows.filter(l => ['signed_in', 'signed_out'].includes(l.status)).length
    let payout = 0
    if (coach.salary_mode === 'fixed') payout = coach.base_salary
    else if (coach.salary_mode === 'base_plus_commission') {
      payout = coach.base_salary + signed * coach.lesson_rate * (1 + coach.commission_rate / 100)
    } else payout = signed * coach.lesson_rate
    return { coach, total_lessons: rows.length, signed_lessons: signed,
      payout: Math.round(payout * 100) / 100, role_label: ROLE_LABELS[coach.role] || coach.role }
  },
}

// ---------------- lessons ----------------

export const lessonStore = {
  list({ date_from = '', date_to = '', coach_id = 0, student_id = 0 } = {}) {
    let rows = publicList('lessons')
    if (date_from) rows = rows.filter(l => l.date >= date_from)
    if (date_to) rows = rows.filter(l => l.date <= date_to)
    if (coach_id) rows = rows.filter(l => l.coach_id === coach_id)
    if (student_id) rows = rows.filter(l => (l.student_ids || []).includes(student_id))
    rows.sort((a, b) => (a.date + a.start_time).localeCompare(b.date + b.start_time))
    return { list: rows }
  },
  today() {
    const t = today()
    const rows = publicList('lessons').filter(l => l.date === t)
      .sort((a, b) => a.start_time.localeCompare(b.start_time))
    const signed = rows.filter(l => ['signed_in', 'signed_out'].includes(l.status)).length
    const studentCount = publicList('students').filter(s => s.status === 'active').length
    return {
      date: t, lesson_count: rows.length, signed_count: signed,
      pending_count: rows.length - signed, student_count: studentCount, lessons: rows,
    }
  },
  week(start, end) {
    const rows = publicList('lessons').filter(l => l.date >= start && l.date <= end)
      .sort((a, b) => (a.date + a.start_time).localeCompare(b.date + b.start_time))
    return { start, end, list: rows }
  },
  detail(id) {
    const lesson = publicList('lessons').find(l => l.id === id)
    if (!lesson) return null
    const all = publicList('students')
    lesson.students = (lesson.student_ids || [])
      .map(sid => all.find(s => s.id === sid))
      .filter(Boolean)
    return lesson
  },
  create(data) {
    const rows = read(K.lessons)
    // 与后端一致：教练同时段冲突检测（不论课程状态）
    const conflict = rows.some(l => !l.deleted && l.coach_id === data.coach_id && l.date === data.date
      && !(l.end_time <= data.start_time || l.start_time >= data.end_time))
    if (conflict) return { __error: '该教练此时段已有排课' }
    const id = nextId()
    rows.push({ id, status: 'pending', location: '', note: '', ...data,
      created_at: stamp(), updated_at: stamp() })
    write(K.lessons, rows)
    return { id }
  },
  update(id, data) {
    write(K.lessons, read(K.lessons).map(l => (l.id === id ? { ...l, ...data, updated_at: stamp() } : l)))
    return { ok: true }
  },
  remove(id) {
    if (read(K.checkins).some(c => c.lesson_id === id)) return { __error: '已有签到记录，不可删除' }
    write(K.lessons, read(K.lessons).filter(l => l.id !== id))
    return { ok: true }
  },
}

// ---------------- checkins ----------------

function deductLesson(studentId) {
  const rows = read(K.packages)
    .filter(p => p.student_id === studentId && !p.deleted && p.status === 'active' && p.remaining_lessons > 0)
    .sort((a, b) => (a.expire_date || '9999').localeCompare(b.expire_date || '9999') || a.id - b.id)
  if (!rows.length) return
  const pkg = rows[0]
  const remaining = pkg.remaining_lessons - 1
  write(K.packages, read(K.packages).map(p => (p.id === pkg.id
    ? { ...p, remaining_lessons: Math.max(remaining, 0), status: remaining <= 0 ? 'exhausted' : 'active', updated_at: stamp() }
    : p)))
  recalcRemaining(studentId)
}

function doCheck(lessonId, studentIds, checkType, note = '') {
  const lesson = publicList('lessons').find(l => l.id === lessonId)
  if (!lesson) return { results: [{ ok: false, reason: '排课不存在' }], lesson_status: 'pending' }
  const valid = new Set(lesson.student_ids || [])
  const records = read(K.checkins)
  const results = []
  const ts = stamp()
  let allOk = studentIds.length > 0
  studentIds.forEach(sid => {
    if (valid.size && !valid.has(sid)) {
      results.push({ student_id: sid, ok: false, reason: '不在该课名单中' })
      allOk = false
      return
    }
    const dup = records.some(c => c.lesson_id === lessonId && c.student_id === sid && c.type === checkType)
    if (dup) {
      results.push({ student_id: sid, ok: false, reason: '已操作过' })
      allOk = false
      return
    }
    records.push({ id: nextId(), student_id: sid, lesson_id: lessonId, type: checkType, timestamp: ts, note })
    results.push({ student_id: sid, ok: true })
    if (checkType === 'check_in') deductLesson(sid)
  })
  write(K.checkins, records)
  if (allOk) {
    const status = checkType === 'check_in' ? 'signed_in' : 'signed_out'
    write(K.lessons, read(K.lessons).map(l => (l.id === lessonId ? { ...l, status, updated_at: ts } : l)))
  }
  const updated = read(K.lessons).find(l => l.id === lessonId)
  return { results, lesson_status: updated ? updated.status : 'pending' }
}

export const checkinStore = {
  checkin(lessonId, studentIds, note = '') {
    return doCheck(lessonId, studentIds, 'check_in', note)
  },
  checkout(lessonId, studentIds, note = '') {
    return doCheck(lessonId, studentIds, 'check_out', note)
  },
  history({ date = '', type = '' } = {}) {
    let rows = read(K.checkins)
    if (date) rows = rows.filter(c => c.timestamp.startsWith(date))
    if (type) rows = rows.filter(c => c.type === type)
    return { list: withStudentNames(rows).sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, 500) }
  },
  pending(date = '') {
    const before = date || today()
    const checkins = read(K.checkins)
    const lessons = publicList('lessons')
    const out = []
    lessons.filter(l => l.date <= before).forEach(l => {
      ;(l.student_ids || []).forEach(sid => {
        const hasIn = checkins.some(c => c.lesson_id === l.id && c.student_id === sid && c.type === 'check_in')
        const hasOut = checkins.some(c => c.lesson_id === l.id && c.student_id === sid && c.type === 'check_out')
        if (hasIn && !hasOut) {
          const inRec = checkins.find(c => c.lesson_id === l.id && c.student_id === sid && c.type === 'check_in')
          out.push({ student_id: sid, lesson_id: l.id, checkin_time: inRec.timestamp,
            date: l.date, start_time: l.start_time, end_time: l.end_time,
            type: l.type, location: l.location })
        }
      })
    })
    return { list: withStudentNames(out).sort((a, b) => b.date.localeCompare(a.date)) }
  },
  todayList() {
    const t = today()
    const checkins = read(K.checkins)
    const names = {}
    read(K.students).forEach(s => { names[s.id] = s.name })
    const rows = publicList('lessons').filter(l => l.date === t)
      .sort((a, b) => a.start_time.localeCompare(b.start_time))
      .map(l => ({
        ...l,
        students: (l.student_ids || []).map(i => ({
          id: i, name: names[i] || `#${i}`,
          checked_in: checkins.some(c => c.lesson_id === l.id && c.student_id === i && c.type === 'check_in'),
          checked_out: checkins.some(c => c.lesson_id === l.id && c.student_id === i && c.type === 'check_out'),
        })),
      }))
    return { date: t, list: rows }
  },
}

// ---------------- packages ----------------

export const packageStore = {
  list({ student_id = 0, status = '' } = {}) {
    refreshExpired()
    let rows = publicList('packages')
    if (student_id) rows = rows.filter(p => p.student_id === student_id)
    if (status) rows = rows.filter(p => p.status === status)
    return { stats: feeStats(), list: withStudentNames(rows).sort((a, b) => b.id - a.id) }
  },
  stats() {
    return feeStats()
  },
  detail(id) {
    return publicList('packages').find(p => p.id === id) || null
  },
  create(data) {
    const rows = read(K.packages)
    const id = nextId()
    rows.push({ id, status: 'active', paid_amount: -1, purchase_date: today(),
      ...data,
      remaining_lessons: data.total_lessons,  // 新包剩余=总课时
      created_at: stamp(), updated_at: stamp(), deleted: 0 })
    write(K.packages, rows)
    recalcRemaining(data.student_id)
    return { id }
  },
  update(id, data) {
    const rows = read(K.packages)
    const pkg = rows.find(p => p.id === id)
    write(K.packages, rows.map(p => (p.id === id
      ? { ...p, ...data, remaining_lessons: data.total_lessons, updated_at: stamp() }
      : p)))
    if (pkg) recalcRemaining(data.student_id || pkg.student_id)
    return { ok: true }
  },
  remove(id) {
    const rows = read(K.packages)
    const pkg = rows.find(p => p.id === id)
    write(K.packages, rows.map(p => (p.id === id ? { ...p, deleted: 1, updated_at: stamp() } : p)))
    if (pkg) recalcRemaining(pkg.student_id)
    return { ok: true }
  },
}

// ---------------- backup ----------------

export function exportBackup(mode) {
  return {
    export_version: 1,
    mode,
    exported_at: stamp(),
    students: allRows('students'),
    coaches: allRows('coaches'),
    lessons: allRows('lessons'),
    lesson_packages: allRows('packages'),
    checkin_records: read(K.checkins),
  }
}

export function importBackup(payload, mode) {
  if ((payload.mode || '') !== mode) return { __error: '模式不匹配' }
  // 运行时构建（K 是动态 getter，按当前模式路由）
  const TABLE_KEYS = { students: K.students, coaches: K.coaches, lessons: K.lessons,
    lesson_packages: K.packages, checkin_records: K.checkins }
  const imported = {}
  Object.entries(TABLE_KEYS).forEach(([table, key]) => {
    const rows = Array.isArray(payload[table]) ? payload[table] : []
    if (!rows.length) { imported[table] = 0; return }
    const local = read(key)
    const idx = {}
    local.forEach((r, i) => { idx[`${r.id}`] = i })
    let count = 0
    rows.forEach(r => {
      if (r.id === undefined || r.id === null) return
      const tsCol = table === 'checkin_records' ? 'timestamp' : 'updated_at'
      const existIdx = idx[`${r.id}`]
      if (existIdx !== undefined) {
        const exist = local[existIdx]
        const newTs = String(r[tsCol] || '')
        const oldTs = String(exist[tsCol] || '')
        if (newTs && newTs >= oldTs) { local[existIdx] = r; count++ }
      } else {
        local.push(r)
        count++
      }
    })
    // 序号推进，避免新 id 冲突
    const maxId = local.reduce((m, r) => Math.max(m, r.id || 0), 0)
    if (maxId > (uni.getStorageSync(K.seq) || 0)) uni.setStorageSync(K.seq, maxId)
    write(key, local)
    imported[table] = count
  })
  // 重建学员剩余课时
  publicList('students').forEach(s => recalcRemaining(s.id))
  return { ok: true, imported }
}
