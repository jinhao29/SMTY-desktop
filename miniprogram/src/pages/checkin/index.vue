<template>
  <view>
    <!-- 未签退提醒 -->
    <view class="card warn-card" v-if="pendingList.length">
      <view class="section-title" style="color:#F59E0B">⚠ 未签退提醒（{{ pendingList.length }}）</view>
      <view v-for="p in pendingList.slice(0, 5)" :key="p.student_id + '-' + p.lesson_id" class="pending-row">
        <view>
          <view class="p-name">{{ p.student_name }}</view>
          <view class="p-sub">{{ p.date }} {{ p.start_time }} 签到后未签退</view>
        </view>
        <view class="p-btn" @tap="quickCheckout(p)">补签退</view>
      </view>
    </view>

    <!-- 今日待签到 -->
    <view class="card">
      <view class="head-row">
        <view class="section-title">今日课程</view>
        <view class="link" @tap="goHistory">签到历史 ›</view>
      </view>
      <view v-if="!todayList.length" class="empty">今天暂无课程</view>
      <view v-for="lesson in todayList" :key="lesson.id" class="lesson-group">
        <view class="lg-head">
          <text class="lg-time">{{ lesson.start_time }}-{{ lesson.end_time }}</text>
          <text class="tag">{{ typeLabel(lesson.type) }}</text>
          <text class="lg-loc" v-if="lesson.location">{{ lesson.location }}</text>
        </view>
        <view v-for="stu in lesson.students" :key="stu.id" class="stu-row">
          <view class="stu-name">
            {{ stu.name }}
            <text v-if="stu.checked_in" class="tag tag-success">已签</text>
            <text v-if="stu.checked_out" class="tag tag-gray">已退</text>
          </view>
          <view class="stu-actions">
            <view v-if="!stu.checked_in" class="p-btn" @tap="doCheckin(lesson, stu)">签到</view>
            <view v-else-if="!stu.checked_out" class="p-btn p-btn-gray" @tap="doCheckout(lesson, stu)">签退</view>
          </view>
        </view>
        <!-- 小班课批量 -->
        <view v-if="lesson.type !== 'private' && lesson.students.length > 1" class="batch-row">
          <view class="p-btn" @tap="batchCheckin(lesson)">全部签到</view>
          <view class="p-btn p-btn-gray" @tap="batchCheckout(lesson)">全部签退</view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow, onPullDownRefresh } from '@dcloudio/uni-app'
import { checkinApi } from '../../api'
import { LESSON_TYPE } from '../../utils/constants'

const todayList = ref([])
const pendingList = ref([])

const typeLabel = (t) => LESSON_TYPE[t] || t

async function load() {
  const [t, p] = await Promise.all([checkinApi.todayList(), checkinApi.pending()])
  todayList.value = t.list
  pendingList.value = p.list
}

async function doCheckin(lesson, stu) {
  await checkinApi.checkin(lesson.id, [stu.id])
  uni.showToast({ title: `${stu.name} 已签到`, icon: 'success' })
  load()
}

async function doCheckout(lesson, stu) {
  await checkinApi.checkout(lesson.id, [stu.id])
  uni.showToast({ title: `${stu.name} 已签退`, icon: 'success' })
  load()
}

async function batchCheckin(lesson) {
  const ids = lesson.students.filter(s => !s.checked_in).map(s => s.id)
  if (!ids.length) return uni.showToast({ title: '已全部签到', icon: 'none' })
  await checkinApi.checkin(lesson.id, ids)
  uni.showToast({ title: '批量签到完成', icon: 'success' })
  load()
}

async function batchCheckout(lesson) {
  const ids = lesson.students.filter(s => s.checked_in && !s.checked_out).map(s => s.id)
  if (!ids.length) return uni.showToast({ title: '无可签退学员', icon: 'none' })
  await checkinApi.checkout(lesson.id, ids)
  uni.showToast({ title: '批量签退完成', icon: 'success' })
  load()
}

async function quickCheckout(p) {
  await checkinApi.checkout(p.lesson_id, [p.student_id])
  uni.showToast({ title: '补签退成功', icon: 'success' })
  load()
}

function goHistory() { uni.navigateTo({ url: '/pages/checkin/history' }) }

onShow(load)
onPullDownRefresh(async () => { await load(); uni.stopPullDownRefresh() })
</script>

<style lang="scss" scoped>
.warn-card { border-left: 3px solid #F59E0B; }
.pending-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0;
  .p-name { font-size: 14px; font-weight: 600; }
  .p-sub { font-size: 11px; color: #8A94A6; margin-top: 2px; } }
.head-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
  .link { font-size: 12px; color: #5B6BF7; } }
.lesson-group { border-top: 1px solid #F0F2F7; padding-top: 10px; margin-top: 10px;
  &:first-of-type { border-top: none; margin-top: 0; }
  .lg-head { display: flex; align-items: center; gap: 8px;
    .lg-time { font-size: 14px; font-weight: 700; }
    .lg-loc { font-size: 11px; color: #8A94A6; } }
  .stu-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0;
    .stu-name { font-size: 14px; display: flex; align-items: center; gap: 6px; } }
  .batch-row { display: flex; gap: 10px; padding: 6px 0 2px; } }
.p-btn {
  background: #5B6BF7; color: #FFF; border-radius: 14px; padding: 5px 16px; font-size: 12px;
  &.p-btn-gray { background: #F0F2F7; color: #5A6478; } }
</style>
