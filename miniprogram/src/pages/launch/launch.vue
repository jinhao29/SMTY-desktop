<template>
  <view class="launch">
    <view class="logo">
      <image class="logo-img" src="/static/logo.png" mode="widthFix" />
    </view>
    <view class="mode-picker">
      <view class="mode-card" :class="{ active: mode === 'shangmen' }" @tap="mode = 'shangmen'">
        <view class="mode-title">上门模式</view>
        <view class="mode-desc">一对一上门教学</view>
      </view>
      <view class="mode-card" :class="{ active: mode === 'club' }" @tap="mode = 'club'">
        <view class="mode-title">俱乐部模式</view>
        <view class="mode-desc">场馆班级教学</view>
      </view>
    </view>
    <view class="btn-primary enter" :class="{ disabled: loading }" @tap="enter">
      {{ token ? '进入系统' : '去登录' }}
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { useModeStore } from '../../stores/mode'

const modeStore = useModeStore()
const mode = ref(modeStore.mode)
const token = uni.getStorageSync('token')
const loading = ref(false)

function enter() {
  if (loading.value) return
  loading.value = true
  modeStore.setMode(mode.value)
  uni.reLaunch({ url: token ? '/pages/home/home' : '/pages/login/login' })
}
</script>

<style lang="scss" scoped>
.launch {
  min-height: 100vh; background: linear-gradient(180deg, #ECF0FF 0%, #F2F4F8 60%);
  display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px;
}
.logo { text-align: center; margin-bottom: 60px;
  .logo-img {
    width: 200px; height: 215px; margin: 0 auto;
    display: block;
    opacity: 0;
    animation: reveal 1.8s cubic-bezier(0.22, 0.61, 0.36, 1) forwards;
  }
}
@keyframes reveal {
  from { opacity: 0; transform: translateY(12px) scale(0.96); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
.mode-picker { display: flex; gap: 14px; width: 100%; }
.mode-card {
  flex: 1; background: #FFF; border: 2px solid transparent; border-radius: 14px; padding: 20px 16px; text-align: center;
  .mode-title { font-size: 16px; font-weight: 600; }
  .mode-desc { font-size: 12px; color: #8A94A6; margin-top: 6px; }
  &.active { border-color: #5B6BF7; background: #F5F7FF; }
}
.enter { width: 100%; margin-top: 48px; }
</style>
