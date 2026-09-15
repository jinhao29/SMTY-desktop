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

// 薪资算法唯一口径在 Android PayoutCalculator（角色决定），小程序不再提供
// salary_mode 选项、不再自算金额——dividend 已移除（两端口径不同，选了就算错钱）
export const SALARY_MODE = {
  fixed: '固定薪资',
  per_lesson: '按课时结算',
  base_plus_commission: '底薪+提成',
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

// 年级选项：与 Android Standards.GRADE_OPTIONS 同源（编码 0-13，13=中考）。
// 小程序存中文标签，Android 导入端 gradeCodeFromLabel 可反向识别。
export const GRADE_OPTIONS = [
  '学龄前(3-7岁)',
  '小学一年级', '小学二年级', '小学三年级',
  '小学四年级', '小学五年级', '小学六年级',
  '初一', '初二', '初三',
  '高一', '高二', '高三',
  '中考',
]

export const PACKAGE_STATUS = {
  active: { label: '生效中', type: 'success' },
  exhausted: { label: '已耗尽', type: 'danger' },
  expired: { label: '已过期', type: 'gray' },
}

export const MODES = {
  shangmen: { label: '上门模式', desc: '一对一上门教学' },
  club: { label: '俱乐部模式', desc: '场馆班级教学' },
}
