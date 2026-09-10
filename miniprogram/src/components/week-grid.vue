<template>
  <view class="week-grid">
    <!-- 星期表头 -->
    <view class="grid-head">
      <view class="head-cell" v-for="(d, i) in dates" :key="d"
            :class="{ today: d === todayStr }">
        <view class="head-label">{{ labels[i] }}</view>
        <view class="head-date">{{ shortDate(d) }}</view>
      </view>
    </view>
    <!-- 课程网格：按日分列，格子按时间排序 -->
    <view class="grid-body">
      <view class="day-col" v-for="d in dates" :key="d" @tap="onColTap(d, $event)">
        <view class="lesson-block" v-for="l in byDay[d]" :key="l.id"
              :class="'st-' + l.status"
              @tap.stop="$emit('lessonTap', l)">
          <view class="l-time">{{ l.start_time }}</view>
          <view class="l-name">{{ studentCount(l) }}人 · {{ typeLabel(l) }}</view>
        </view>
        <view class="empty-slot" @tap.stop="$emit('emptyTap', d)">+</view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { WEEK_LABELS, shortDate, today } from '../utils/date'
import { LESSON_TYPE } from '../utils/constants'

const props = defineProps({
  dates: { type: Array, required: true },   // 7 个日期字符串
  lessons: { type: Array, default: () => [] },
})
defineEmits(['emptyTap', 'lessonTap'])

const labels = WEEK_LABELS
const todayStr = today()

const byDay = computed(() => {
  const map = {}
  for (const d of props.dates) map[d] = []
  for (const l of props.lessons) {
    if (map[l.date]) map[l.date].push(l)
  }
  for (const d of Object.keys(map)) map[d].sort((a, b) => a.start_time.localeCompare(b.start_time))
  return map
})

const studentCount = (l) => (l.student_ids || []).length
const typeLabel = (l) => LESSON_TYPE[l.type] || ''

function onColTap(d, e) {
  if (e.target.classList && e.target.classList.contains('lesson-block')) return
}
</script>

<style lang="scss" scoped>
.week-grid { background: #FFFFFF; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin: 12px 16px; overflow: hidden; }
.grid-head {
  display: flex; border-bottom: 1px solid #F0F2F7;
  .head-cell { flex: 1; text-align: center; padding: 10px 0;
    .head-label { font-size: 12px; color: #8A94A6; }
    .head-date { font-size: 13px; font-weight: 600; color: #1A2233; margin-top: 2px; }
    &.today .head-date { color: #5B6BF7; }
  }
}
.grid-body { display: flex; min-height: 320px;
  .day-col { flex: 1; border-right: 1px solid #F7F8FC; padding: 6px 3px; position: relative;
    &:last-child { border-right: none; }
    .lesson-block {
      background: #ECF0FF; border-radius: 8px; padding: 6px 4px; margin-bottom: 6px;
      .l-time { font-size: 10px; color: #5B6BF7; font-weight: 700; }
      .l-name { font-size: 10px; color: #1A2233; margin-top: 2px; }
      &.st-signed_in { background: #E8F9F0; .l-time { color: #34C77B; } }
      &.st-signed_out { background: #F0F2F7; .l-time { color: #8A94A6; } }
    }
    .empty-slot {
      text-align: center; color: #C0C7D4; font-size: 18px; padding: 8px 0;
    }
  }
}
</style>
