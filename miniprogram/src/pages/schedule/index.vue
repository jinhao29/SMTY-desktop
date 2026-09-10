<template>
  <view class="tab-page">
    <!-- 周切换 -->
    <view class="week-nav">
      <view class="nav-btn" @tap="shiftWeek(-1)">‹ 上一周</view>
      <view class="nav-title" @tap="goToday">{{ weekLabel }}</view>
      <view class="nav-right" @tap="goBatch">批量导入</view>
    </view>

    <week-grid :dates="dates" :lessons="lessons"
               @emptyTap="onEmptyTap"
               @lessonTap="onLessonTap" />
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { lessonApi } from '../../api'
import { weekDates, addDays, today, fmt } from '../../utils/date'
import WeekGrid from '../../components/week-grid.vue'

const monday = ref(startOfWeek(today()))
const dates = computed(() => weekDates(monday.value))
const weekLabel = computed(() => `${monday.value.slice(5)} ~ ${addDays(monday.value, 6).slice(5)}`)
const lessons = ref([])

function startOfWeek(dateStr) { return weekDates(dateStr)[0] }

async function load() {
  const res = await lessonApi.week(monday.value, addDays(monday.value, 6))
  lessons.value = res.list
}

function shiftWeek(n) {
  monday.value = addDays(monday.value, n * 7)
  load()
}
function goToday() { monday.value = startOfWeek(today()); load() }
function goBatch() { uni.navigateTo({ url: '/pages/schedule/batch-import' }) }

function onEmptyTap(d) { uni.navigateTo({ url: `/pages/schedule/lesson-edit?date=${d}` }) }
function onLessonTap(l) { uni.navigateTo({ url: `/pages/schedule/lesson-edit?id=${l.id}&date=${l.date}` }) }

onShow(load)
</script>

<style lang="scss" scoped>
.week-nav {
  display: flex; align-items: center; justify-content: space-between;
  margin: 12px 16px;
  .nav-btn { font-size: 13px; color: #5B6BF7; }
  .nav-title { font-size: 15px; font-weight: 600; }
  .nav-right { font-size: 12px; color: #5B6BF7; font-weight: 600;
    padding: 4px 10px; border: 1px solid #5B6BF7; border-radius: 14px; }
}
</style>
