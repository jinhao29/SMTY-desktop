<template>
  <view class="student-card card" @tap="$emit('tap', student)">
    <view class="avatar">{{ student.name?.slice(0, 1) }}</view>
    <view class="info">
      <view class="row-1">
        <text class="name">{{ student.name }}</text>
        <text class="tag" :class="'tag-' + statusInfo.type">{{ statusInfo.label }}</text>
        <text v-if="student.class_group" class="tag">{{ student.class_group }}</text>
      </view>
      <view class="row-2">
        <text>{{ student.grade || '未填年级' }}</text>
        <text v-if="student.address" class="addr"> · {{ student.address }}</text>
      </view>
    </view>
    <view class="right">
      <view class="remain">{{ student.remaining_lessons }}</view>
      <view class="remain-label">剩余课时</view>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { STUDENT_STATUS } from '../utils/constants'

const props = defineProps({ student: { type: Object, required: true } })
defineEmits(['tap'])

const statusInfo = computed(() => STUDENT_STATUS[props.student.status] || { label: props.student.status, type: 'gray' })
</script>

<style lang="scss" scoped>
.student-card { display: flex; align-items: center; }
.avatar {
  width: 42px; height: 42px; border-radius: 50%;
  background: #ECF0FF; color: #5B6BF7;
  font-size: 16px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
}
.info { flex: 1; margin-left: 12px; overflow: hidden;
  .row-1 { display: flex; align-items: center; gap: 6px;
    .name { font-size: 15px; font-weight: 600; }
  }
  .row-2 { font-size: 12px; color: #8A94A6; margin-top: 4px;
    .addr { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  }
}
.right { text-align: center; margin-left: 8px;
  .remain { font-size: 18px; font-weight: 700; color: #5B6BF7; }
  .remain-label { font-size: 10px; color: #8A94A6; }
}
</style>
