/** 常量枚举（与后端 / Android 端对齐） */

export const STUDENT_STATUS = {
  active: { label: '在读', type: 'success' },
  paused: { label: '停课', type: 'warning' },
  graduated: { label: '毕业', type: 'gray' },
}

export const COACH_ROLE = {
  fulltime: '全职',
  parttime: '兼职',
  partner_level1: '一级合伙人',
  partner_level2: '二级合伙人',
}

export const COACH_STATUS = {
  active: { label: '在职', type: 'success' },
  on_leave: { label: '休假', type: 'warning' },
  inactive: { label: '离职', type: 'gray' },
}

export const SALARY_MODE = {
  fixed: '固定薪资',
  per_lesson: '按课时结算',
  base_plus_commission: '底薪+提成',
  dividend: '分红',
}

export const LESSON_TYPE = {
  private: '私教',
  small_group: '小班课',
  group: '团课',
}

export const LESSON_STATUS = {
  pending: { label: '待上课', type: 'gray' },
  signed_in: { label: '已签到', type: 'success' },
  signed_out: { label: '已签退', type: 'default' },
}

export const CLASS_GROUPS = ['U8', 'U10', 'U12']

export const PACKAGE_STATUS = {
  active: { label: '生效中', type: 'success' },
  exhausted: { label: '已耗尽', type: 'danger' },
  expired: { label: '已过期', type: 'gray' },
}

export const MODES = {
  shangmen: { label: '上门模式', desc: '一对一上门教学' },
  club: { label: '俱乐部模式', desc: '场馆班级教学' },
}
