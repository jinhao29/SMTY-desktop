<template>
  <view class="lesson-card card" @tap="$emit('tap', lesson)">
    <view class="time">
      <view class="start">{{ lesson.start_time }}</view>
      <view class="end">{{ lesson.end_time }}</view>
    </view>
    <view class="divider" />
    <view class="body">
      <view class="row-1">
        <text class="tag">{{ typeLabel }}</text>
        <text class="tag" :class="'tag-' + (statusInfo.type === 'default' ? 'gray' : statusInfo.type)">{{ statusInfo.label }}</text>
        <text class="students">{{ studentNames }}</text>
      </view>
      <view class="row-2">
        <text v-if="lesson.location">📍 {{ lesson.location }}</text>
        <text v-if="coachName"> · 教练：{{ coachName }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { LESSON_TYPE, LESSON_STATUS } from '../utils/constants'

const props = defineProps({
  lesson: { type: Object, required: true },
  coachName: { type: String, default: '' },
})
defineEmits(['tap'])

const typeLabel = computed(() => LESSON_TYPE[props.lesson.type] || props.lesson.type)
const statusInfo = computed(() => LESSON_STATUS[props.lesson.status] || { label: props.lesson.status, type: 'gray' })
const studentNames = computed(() => {
  const list = props.lesson.students || props.lesson.student_ids || []
  return list.length ? `${list.length} 名学员` : ''
})
</script>

<style lang="scss" scoped>
.lesson-card { display: flex; }
.time {
  width: 56px; text-align: center;
  .start { font-size: 15px; font-weight: 700; color: #1A2233; }
  .end { font-size: 11px; color: #8A94A6; margin-top: 2px; }
}
.divider { width: 1px; background: #F0F2F7; margin: 0 12px; }
.body { flex: 1;
  .row-1 { display: flex; align-items: center; gap: 6px;
    .students { margin-left: auto; font-size: 12px; color: #8A94A6; }
  }
  .row-2 { font-size: 12px; color: #8A94A6; margin-top: 6px; }
}
</style>
