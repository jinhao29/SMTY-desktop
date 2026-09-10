<template>
  <view class="page">
    <!-- 前置选择 -->
    <view class="card">
      <view class="form-item form-row">
        <view>
          <text class="form-label">教练（整批共用）</text>
          <picker :range="coachOptions" range-key="label" @change="(e) => form.coach_id = coachOptions[e.detail.value].id">
            <view class="form-input picker">{{ coachName || '请选择教练' }}</view>
          </picker>
        </view>
        <view>
          <text class="form-label">「周X」归属</text>
          <picker :range="weekOptions" range-key="label" @change="(e) => weekIdx = +e.detail.value">
            <view class="form-input picker">{{ weekOptions[weekIdx].label }}</view>
          </picker>
        </view>
      </view>

      <view class="form-item">
        <text class="form-label">课程计划（每行一节课）</text>
        <textarea class="form-textarea mono" v-model="text" :maxlength="-1"
                  placeholder="示例：&#10;周一 15:00-16:00 陈小明 私教 雅居乐花园&#10;周二 17:00 林小雨、黄浩然 小班课 大学城体育中心&#10;9/18 10:00 王一" />
        <view class="img-row">
          <view class="link-btn" @tap="ocrImage">📷 从计划图识别</view>
          <text class="img-hint">{{ isServer ? '拍照/相册均可' : '本地模式不支持，请复制文字' }}</text>
        </view>
      </view>

      <view class="btn-primary" :class="{ disabled: parsing || !text.trim() }" @tap="parse">解析预览</view>
    </view>

    <!-- 解析结果 -->
    <view v-if="items.length" class="card">
      <view class="section-title">解析结果（{{ items.length }} 节）</view>
      <view v-for="(it, i) in items" :key="i" class="p-item" :class="{ missing: it.missing }">
        <view class="p-main">
          <text class="p-date">{{ it.date }} {{ weekdayLabel(it.date) }}</text>
          <text class="p-time">{{ it.start_time }}-{{ it.end_time }}</text>
        </view>
        <view class="p-sub">
          <text :class="{ warn: it.missing }">{{ studentLabel(it) }}</text>
          <text v-if="it.location"> · {{ it.location }}</text>
          <text class="p-type">{{ TYPE_LABEL[it.type] }}</text>
          <text class="p-del" @tap="items.splice(i, 1)">删除</text>
        </view>
      </view>
      <view v-if="errors.length" class="err-box">
        <view class="err-title">{{ errors.length }} 行未能识别：</view>
        <view v-for="(e, i) in errors" :key="i" class="err-line">{{ e.line }} → {{ e.reason }}</view>
      </view>
      <view class="btn-primary" :class="{ disabled: creating }" @tap="createAll">
        {{ creating ? '创建中…' : `创建 ${creatableCount} 节课` }}
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { lessonApi, coachApi, studentApi } from '../../api'
import { BASE_URL } from '../../utils/request'
import { parseSchedule } from '../../utils/schedule-parser'
import { required } from '../../utils/validator'

const TYPE_LABEL = { private: '私教', small_group: '小班课', group: '团课' }
const WEEK_CN = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

const text = ref('')
const items = ref([])
const errors = ref([])
const students = ref([])
const coaches = ref([])
const coach_id = ref(null)
const weekIdx = ref(1) // 默认下周
const parsing = ref(false)
const creating = ref(false)
const isServer = uni.getStorageSync('authMode') === 'server'

const form = reactive({ coach_id: null })
const coachOptions = computed(() => coaches.value.map(c => ({ id: c.id, label: c.name })))
const coachName = computed(() => coachOptions.value.find(c => c.id === form.coach_id)?.label || '')

// 本周一 / 下周一（周一起始）
function mondayOffset(weeks) {
  const d = new Date()
  const dow = d.getDay() === 0 ? 7 : d.getDay()
  d.setDate(d.getDate() - dow + 1 + weeks * 7)
  return d.toISOString().slice(0, 10)
}
const weekOptions = [
  { label: '本周', value: mondayOffset(0) },
  { label: '下周', value: mondayOffset(1) },
]
const weekStart = computed(() => weekOptions[weekIdx.value].value)

const creatableCount = computed(() => items.value.filter(i => !i.missing).length)

function weekdayLabel(iso) {
  return WEEK_CN[new Date(iso + 'T00:00:00').getDay()]
}

function studentLabel(it) {
  if (!it.student_ids.length) return '⚠ 未匹配到学员'
  return it.student_ids.map(id => students.value.find(s => s.id === id)?.name).join('、')
}

function parse() {
  if (parsing.value || !text.value.trim()) return
  parsing.value = true
  try {
    const r = parseSchedule(text.value, students.value, weekStart.value)
    items.value = r.items
    errors.value = r.errors
    if (!r.items.length && !r.errors.length) uni.showToast({ title: '没有可识别的内容', icon: 'none' })
  } finally { parsing.value = false }
}

/** 图片 OCR → 文本（仅服务器模式；本地模式无后端识别能力） */
function ocrImage() {
  if (!isServer) {
    uni.showToast({ title: '图片识别需连接服务器，可复制文字导入', icon: 'none', duration: 2500 })
    return
  }
  uni.chooseImage({
    count: 1, sizeType: ['compressed'],
    success: ({ tempFilePaths: [path] }) => {
      uni.showLoading({ title: '识别中', mask: true })
      uni.uploadFile({
        url: BASE_URL + '/api/v1/ocr/image',
        filePath: path, name: 'file',
        header: { Authorization: 'Bearer ' + (uni.getStorageSync('token') || '') },
        success: (res) => {
          uni.hideLoading()
          try {
            const d = JSON.parse(res.data)
            if (res.statusCode === 200 && d.text) {
              text.value = text.value ? text.value + '\n' + d.text : d.text
              uni.showToast({ title: `识别到 ${d.count} 行`, icon: 'success' })
            } else {
              uni.showToast({ title: d.detail || '未识别到文字', icon: 'none' })
            }
          } catch (e) { uni.showToast({ title: '识别结果异常', icon: 'none' }) }
        },
        fail: () => { uni.hideLoading(); uni.showToast({ title: '上传失败', icon: 'none' }) },
      })
    },
  })
}

async function createAll() {
  if (creating.value) return
  if (!required(form.coach_id, '教练')) return
  const todo = items.value.filter(i => !i.missing)
  if (!todo.length) { uni.showToast({ title: '没有可创建的课程（缺学员）', icon: 'none' }); return }
  creating.value = true
  let ok = 0
  const failed = []
  for (const it of todo) {
    try {
      await lessonApi.create({
        date: it.date, start_time: it.start_time, end_time: it.end_time,
        student_ids: it.student_ids, coach_id: form.coach_id,
        type: it.type, location: it.location || '',
      })
      ok++
    } catch (e) { failed.push(it.raw) }
  }
  creating.value = false
  uni.showModal({
    title: '导入完成',
    content: `成功 ${ok} 节${failed.length ? `，失败 ${failed.length} 节（时段冲突等）` : ''}`,
    showCancel: false,
    success: () => { if (ok) uni.navigateBack() },
  })
}

onLoad(async () => {
  const [s, c] = await Promise.all([studentApi.list({ page_size: 200 }), coachApi.list({ page_size: 100 })])
  students.value = s.list
  coaches.value = c.list.filter(c => c.status === 'active')
})
</script>

<style lang="scss" scoped>
.page { padding-bottom: 40px; }
.mono { font-size: 13px; min-height: 140px; }
.img-row { display: flex; align-items: center; gap: 10px; margin-top: 8px;
  .link-btn { color: #5B6BF7; font-size: 13px; font-weight: 600; }
  .img-hint { font-size: 11px; color: #8A94A6; } }
.section-title { margin-bottom: 10px; font-size: 14px; font-weight: 600; color: #1A2233; }
.p-item { padding: 10px 0; border-bottom: 1px solid #F2F4F8;
  &.missing { background: #FFFBEB; margin: 0 -12px; padding: 10px 12px; border-radius: 8px; }
  .p-main { display: flex; gap: 10px; font-size: 14px; font-weight: 600; color: #1A2233;
    .p-time { color: #5B6BF7; } }
  .p-sub { display: flex; flex-wrap: wrap; gap: 4px; font-size: 12px; color: #5A6478; margin-top: 4px;
    .warn { color: #F59E0B; font-weight: 600; }
    .p-type { color: #8A94A6; }
    .p-del { margin-left: auto; color: #EF4444; } } }
.err-box { background: #FEF2F2; border-radius: 8px; padding: 10px 12px; margin: 10px 0;
  .err-title { font-size: 12px; color: #EF4444; font-weight: 600; }
  .err-line { font-size: 11px; color: #B91C1C; margin-top: 4px; word-break: break-all; } }
.btn-primary { background: #5B6BF7; color: #FFF; border-radius: 12px; height: 44px;
  display: flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 600;
  &.disabled { opacity: 0.5; } }
</style>
