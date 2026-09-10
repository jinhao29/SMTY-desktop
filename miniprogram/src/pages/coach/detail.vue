<template>
  <view v-if="c">
    <!-- 档案 -->
    <view class="card">
      <view class="head">
        <view class="avatar">{{ c.name.slice(0, 1) }}</view>
        <view class="head-info">
          <view class="name-row">
            <text class="name">{{ c.name }}</text>
            <text class="tag" :class="'tag-' + (statusInfo.type === 'default' ? 'gray' : statusInfo.type)">{{ statusInfo.label }}</text>
          </view>
          <view class="sub">{{ roleLabel }} · {{ c.phone || '未填电话' }}</view>
        </view>
      </view>
      <view class="cell"><view class="cell-label">薪资模式</view><view class="cell-value">{{ salaryLabel }}</view></view>
      <view class="cell"><view class="cell-label">课时费单价</view><view class="cell-value">¥{{ c.lesson_rate }}/课时</view></view>
      <view class="cell" v-if="c.base_salary"><view class="cell-label">底薪</view><view class="cell-value">¥{{ c.base_salary }}</view></view>
      <view class="cell"><view class="cell-label">擅长项目</view><view class="cell-value">{{ specialties || '—' }}</view></view>
      <view class="cell" v-if="c.phone"><view class="cell-label">联系电话</view><view class="cell-value link" @tap="copyPhone">{{ c.phone }}（点按复制）</view></view>
    </view>

    <!-- 课时统计与薪资结算 -->
    <view class="card">
      <view class="section-title">课时统计</view>
      <view class="nums">
        <view class="num-item"><view class="v">{{ payout.total_lessons }}</view><view class="l">累计排课</view></view>
        <view class="num-item"><view class="v">{{ payout.signed_lessons }}</view><view class="l">已上课时</view></view>
        <view class="num-item"><view class="v" style="color:#5B6BF7">¥{{ payout.payout }}</view><view class="l">应结算薪资</view></view>
      </view>
    </view>

    <!-- 排班表 -->
    <view class="card">
      <view class="section-title">近期排班</view>
      <view v-if="!schedule.length" class="empty">暂无排班</view>
      <view v-for="l in schedule.slice(0, 15)" :key="l.id" class="cell">
        <view class="cell-label">{{ l.date }} {{ l.start_time }}-{{ l.end_time }}</view>
        <view class="cell-value">{{ (l.student_ids || []).length }} 名学员</view>
      </view>
    </view>

    <view class="edit-btn" @tap="goEdit">编辑资料</view>
  </view>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { coachApi } from '../../api'
import { COACH_ROLE, COACH_STATUS, SALARY_MODE } from '../../utils/constants'

const c = ref(null)
const payout = reactive({ total_lessons: 0, signed_lessons: 0, payout: 0 })
const schedule = ref([])
const id = ref(0)

const roleLabel = computed(() => (c.value && (COACH_ROLE[c.value.role] || c.value.role)) || '')
const statusInfo = computed(() => (c.value && (COACH_STATUS[c.value.status] || { label: c.value.status, type: 'gray' })) || {})
const salaryLabel = computed(() => (c.value && (SALARY_MODE[c.value.salary_mode] || c.value.salary_mode)) || '')
const specialties = computed(() => {
  if (!c.value) return ''
  return Array.isArray(c.value.specialties) ? c.value.specialties.join(' / ') : ''
})

async function load() {
  c.value = await coachApi.detail(id.value)
  const p = await coachApi.payout(id.value)
  Object.assign(payout, { total_lessons: p.total_lessons, signed_lessons: p.signed_lessons, payout: p.payout })
  const s = await coachApi.schedule(id.value)
  schedule.value = s.list
}

function copyPhone() {
  uni.setClipboardData({ data: c.value.phone, success: () => uni.showToast({ title: '已复制', icon: 'success' }) })
}
function goEdit() { uni.navigateTo({ url: `/pages/coach/edit?id=${id.value}` }) }

onLoad((q) => { id.value = Number(q.id) })
onShow(load)
</script>

<style lang="scss" scoped>
.head { display: flex; align-items: center; margin-bottom: 8px;
  .avatar { width: 52px; height: 52px; border-radius: 50%; background: #ECF0FF; color: #5B6BF7;
    font-size: 20px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
  .head-info { margin-left: 12px;
    .name-row { display: flex; align-items: center; gap: 6px; }
    .name { font-size: 18px; font-weight: 700; }
    .sub { font-size: 12px; color: #8A94A6; margin-top: 4px; } }
}
.nums { display: flex; text-align: center; padding-top: 6px;
  .num-item { flex: 1;
    .v { font-size: 18px; font-weight: 700; }
    .l { font-size: 11px; color: #8A94A6; margin-top: 2px; } }
}
.link { color: #5B6BF7; }
.edit-btn {
  margin: 8px 16px 32px; text-align: center; line-height: 44px; height: 44px;
  background: #FFF; border: 1px solid #5B6BF7; color: #5B6BF7; border-radius: 12px; font-size: 15px;
}
</style>
