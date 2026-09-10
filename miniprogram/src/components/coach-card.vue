<template>
  <view class="coach-card card" @tap="$emit('tap', coach)">
    <view class="avatar">{{ coach.name?.slice(0, 1) }}</view>
    <view class="info">
      <view class="row-1">
        <text class="name">{{ coach.name }}</text>
        <text class="tag" :class="'tag-' + (statusInfo.type === 'default' ? 'gray' : statusInfo.type)">{{ statusInfo.label }}</text>
      </view>
      <view class="row-2">
        <text class="tag">{{ roleLabel }}</text>
        <text v-for="s in specialties.slice(0, 2)" :key="s" class="tag tag-gray">{{ s }}</text>
      </view>
    </view>
    <view class="arrow">›</view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { COACH_ROLE, COACH_STATUS } from '../utils/constants'

const props = defineProps({ coach: { type: Object, required: true } })
defineEmits(['tap'])

const roleLabel = computed(() => COACH_ROLE[props.coach.role] || props.coach.role)
const statusInfo = computed(() => COACH_STATUS[props.coach.status] || { label: props.coach.status, type: 'gray' })
const specialties = computed(() => (Array.isArray(props.coach.specialties) ? props.coach.specialties : []))
</script>

<style lang="scss" scoped>
.coach-card { display: flex; align-items: center; }
.avatar {
  width: 42px; height: 42px; border-radius: 50%;
  background: #ECF0FF; color: #5B6BF7;
  font-size: 16px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
}
.info { flex: 1; margin-left: 12px;
  .row-1 { display: flex; align-items: center; gap: 6px;
    .name { font-size: 15px; font-weight: 600; }
  }
  .row-2 { display: flex; gap: 6px; margin-top: 4px; }
}
.arrow { color: #C0C7D4; font-size: 20px; }
</style>
