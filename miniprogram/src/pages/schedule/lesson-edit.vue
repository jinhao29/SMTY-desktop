<template>
  <view class="page">
    <view class="card">
      <view class="form-item">
        <text class="form-label">课程日期</text>
        <picker mode="date" :value="form.date" @change="(e) => form.date = e.detail.value">
          <view class="form-input picker">{{ form.date || '请选择日期' }}</view>
        </picker>
      </view>
      <view class="form-item form-row">
        <view>
          <text class="form-label">开始时间</text>
          <picker mode="time" :value="form.start_time" @change="onStartChange">
            <view class="form-input picker">{{ form.start_time || '开始' }}</view>
          </picker>
        </view>
        <view>
          <text class="form-label">结束时间{{ duration > 0 ? '（自动）' : '' }}</text>
          <picker v-if="duration < 0" mode="time" :value="form.end_time" @change="(e) => form.end_time = e.detail.value">
            <view class="form-input picker">{{ form.end_time || '结束' }}</view>
          </picker>
          <view v-else class="form-input picker auto-end">{{ form.end_time || '结束' }}</view>
        </view>
      </view>
      <view class="form-item">
        <text class="form-label">上课时长</text>
        <view class="chips">
          <view v-for="d in DURATIONS" :key="d.m"
                class="chip" :class="{ active: duration === d.m }"
                @tap="onDurationTap(d.m)">{{ d.label }}</view>
          <view class="chip" :class="{ active: duration < 0 }" @tap="duration = -1">自定义</view>
        </view>
      </view>
      <view class="form-item">
        <text class="form-label">课程类型</text>
        <view class="chips">
          <view v-for="(label, key) in LESSON_TYPE" :key="key"
                class="chip" :class="{ active: form.type === key }"
                @tap="onTypeChange(key)">{{ label }}</view>
        </view>
      </view>
      <view class="form-item">
        <text class="form-label">教练</text>
        <picker :range="coachOptions" range-key="label" @change="(e) => form.coach_id = coachOptions[e.detail.value].id">
          <view class="form-input picker">{{ coachName || '请选择教练' }}</view>
        </picker>
      </view>
      <view class="form-item">
        <text class="form-label">学员{{ form.type === 'private' ? '（单选）' : '（可多选）' }}</text>
        <view class="chips">
          <view v-for="s in students" :key="s.id"
                class="chip" :class="{ active: selectedStudents.includes(s.id) }"
                @tap="toggleStudent(s.id)">{{ s.name }}</view>
        </view>
      </view>
      <view class="form-item">
        <text class="form-label">地点</text>
        <input class="form-input" v-model="form.location" placeholder="小区 / 场馆" />
      </view>
      <view class="form-item">
        <text class="form-label">备注</text>
        <textarea class="form-textarea" v-model="form.note" placeholder="选填" />
      </view>
    </view>

    <view class="actions">
      <view v-if="lessonId" class="btn-danger" @tap="removeLesson">删除</view>
      <view class="btn-primary save" :class="{ disabled: saving }" @tap="save">{{ lessonId ? '保存' : '创建排课' }}</view>
    </view>
  </view>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { lessonApi, coachApi, studentApi } from '../../api'
import { LESSON_TYPE } from '../../utils/constants'
import { required } from '../../utils/validator'

const lessonId = ref(0)
const students = ref([])
const coaches = ref([])
const selectedStudents = ref([])
const saving = ref(false)

const form = reactive({
  date: '', start_time: '', end_time: '10:00',
  type: 'private', coach_id: null, location: '', note: '',
})

// 上课时长（分钟）：选开始时间后自动算结束时间；-1 = 自定义结束时间
const DURATIONS = [
  { m: 30, label: '30分钟' },
  { m: 60, label: '1小时' },
  { m: 90, label: '1.5小时' },
  { m: 120, label: '2小时' },
]
const duration = ref(60)

/** "HH:MM" + 分钟 → "HH:MM"（支持跨午夜） */
function plusMinutes(hhmm, mins) {
  const [h, m] = hhmm.split(':').map(Number)
  const t = (h * 60 + m + mins) % 1440
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`
}

function applyDuration() {
  if (duration.value > 0 && form.start_time) form.end_time = plusMinutes(form.start_time, duration.value)
}

function onStartChange(e) {
  form.start_time = e.detail.value
  applyDuration()
}

function onDurationTap(m) {
  duration.value = m
  applyDuration()
}

/** 由已有 start/end 反推时长预设（编辑回填用） */
function inferDuration() {
  if (!form.start_time || !form.end_time) return
  const [sh, sm] = form.start_time.split(':').map(Number)
  const [eh, em] = form.end_time.split(':').map(Number)
  let diff = eh * 60 + em - (sh * 60 + sm)
  if (diff < 0) diff += 1440 // 跨午夜
  duration.value = DURATIONS.some(d => d.m === diff) ? diff : -1
}

const coachOptions = computed(() => coaches.value.map(c => ({ id: c.id, label: c.name })))
const coachName = computed(() => coachOptions.value.find(c => c.id === form.coach_id)?.label || '')

function onTypeChange(key) {
  form.type = key
  if (key === 'private' && selectedStudents.value.length > 1) {
    selectedStudents.value = selectedStudents.value.slice(0, 1)
  }
}

function toggleStudent(id) {
  const i = selectedStudents.value.indexOf(id)
  if (i >= 0) { selectedStudents.value.splice(i, 1); return }
  if (form.type === 'private') selectedStudents.value = [id]
  else selectedStudents.value.push(id)
}

async function load() {
  const [s, c] = await Promise.all([studentApi.list({ page_size: 200 }), coachApi.list({ page_size: 100 })])
  students.value = s.list
  coaches.value = c.list.filter(c => c.status === 'active')
  if (!lessonId.value) return
  const l = await lessonApi.detail(lessonId.value)
  Object.assign(form, {
    date: l.date, start_time: l.start_time, end_time: l.end_time,
    type: l.type, coach_id: l.coach_id, location: l.location, note: l.note,
  })
  inferDuration()
  selectedStudents.value = l.student_ids || []
}

async function save() {
  if (saving.value) return
  if (!required(form.date, '日期')) return
  if (!required(form.start_time, '开始时间')) return
  if (!form.coach_id) { uni.showToast({ title: '请选择教练', icon: 'none' }); return }
  if (!selectedStudents.value.length) { uni.showToast({ title: '请选择学员', icon: 'none' }); return }
  saving.value = true
  try {
    const payload = { ...form, student_ids: selectedStudents.value }
    if (lessonId.value) await lessonApi.update(lessonId.value, payload)
    else await lessonApi.create(payload)
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 500)
  } finally { saving.value = false }
}

function removeLesson() {
  uni.showModal({
    title: '删除排课', content: '确定删除这节排课吗？',
    success: async (r) => {
      if (r.confirm) {
        await lessonApi.remove(lessonId.value)
        uni.navigateBack()
      }
    },
  })
}

onLoad((q) => {
  lessonId.value = Number(q.id || 0)
  form.date = q.date || ''
})
onShow(load)
</script>

<style lang="scss" scoped>
.page { padding-bottom: 90px; }
.picker { line-height: 44px; }
/* 自动计算的结束时间：视觉上与手选区分 */
.auto-end { color: #5B6BF7; background: #F5F7FF; }
.chips { display: flex; flex-wrap: wrap; gap: 8px;
  .chip { padding: 6px 14px; border-radius: 16px; background: #F7F8FC; font-size: 13px; color: #5A6478;
    &.active { background: #ECF0FF; color: #5B6BF7; font-weight: 600; } }
}
.actions {
  position: fixed; bottom: 0; left: 0; right: 0;
  display: flex; gap: 12px; padding: 12px 16px calc(12px + env(safe-area-inset-bottom));
  background: #FFF; box-shadow: 0 -2px 8px rgba(0,0,0,0.04);
  .btn-danger { flex: 0.5; background: #FDECEC; color: #EF4444; border-radius: 12px; text-align: center; line-height: 44px; font-size: 15px; }
  .save { flex: 1.5; }
}
</style>
