<template>
  <view class="tab-page">
    <!-- 分段切换：学员 / 教练 -->
    <view class="seg">
      <view class="seg-item" :class="{ active: tab === 'student' }" @tap="switchSeg('student')">学员</view>
      <view class="seg-item" :class="{ active: tab === 'coach' }" @tap="switchSeg('coach')">教练</view>
    </view>

    <student-panel v-show="tab === 'student'" ref="studentRef" />
    <coach-panel v-show="tab === 'coach'" ref="coachRef" />
  </view>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import StudentPanel from '../../components/student-panel.vue'
import CoachPanel from '../../components/coach-panel.vue'

const tab = ref('student')
const studentRef = ref()
const coachRef = ref()
let ready = false

async function refresh() {
  await nextTick()
  const panel = tab.value === 'student' ? studentRef.value : coachRef.value
  if (panel) panel.load()
}

function switchSeg(name) {
  if (tab.value === name) return
  tab.value = name
  refresh()
}

onMounted(() => { ready = true; refresh() })
onShow(() => {
  // 首页快捷入口跳转前会写入 manage_tab，用于定位到教练/学员段
  const t = uni.getStorageSync('manage_tab')
  if (t === 'student' || t === 'coach') {
    uni.removeStorageSync('manage_tab')
    tab.value = t
  }
  if (ready) refresh()
})
</script>

<style lang="scss" scoped>
.seg { display: flex; gap: 4px; margin: 12px 16px 0; background: #FFF; border-radius: 12px; padding: 4px;
  .seg-item { flex: 1; height: 34px; border-radius: 9px; font-size: 14px; color: #5A6478;
    display: flex; align-items: center; justify-content: center;
    &.active { background: #5B6BF7; color: #FFF; font-weight: 600; } }
}
</style>
