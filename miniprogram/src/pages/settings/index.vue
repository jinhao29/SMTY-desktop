<template>
  <view class="tab-page">
    <view class="card">
      <view class="cell">
        <view class="cell-label">当前模式</view>
        <view class="cell-value">{{ modeInfo.label }} · {{ modeInfo.desc }}</view>
      </view>
      <view class="cell link" @tap="userStore.changeAvatar()">
        <view class="cell-label">个人头像</view>
        <view class="cell-value avatar-cell">
          <image v-if="userStore.avatar" :src="userStore.avatar" class="mini-avatar" />
          <view v-else class="mini-fallback">{{ userStore.displayName.charAt(0) }}</view>
          点击更换
        </view>
      </view>
      <view class="cell">
        <view class="cell-label">登录账号</view>
        <view class="cell-value">{{ userStore.displayName }}<text v-if="user?.phone"> · {{ user.phone }}</text></view>
      </view>
      <view class="cell link" @tap="confirmSwitchDataSource">
        <view class="cell-label">数据来源</view>
        <view class="cell-value">
          {{ isLocal ? '本地模式（数据存本机）' : '服务器 API' }} <text class="arrow">›</text>
        </view>
      </view>
    </view>

    <view class="card">
      <view class="cell link" @tap="goCoach()">
        <view class="cell-label">教练管理</view><view class="arrow">›</view>
      </view>
      <view class="cell link" @tap="go('/pages/package/list')">
        <view class="cell-label">课时与课程包</view><view class="arrow">›</view>
      </view>
      <view class="cell link" @tap="go('/pages/checkin/history')">
        <view class="cell-label">签到历史</view><view class="arrow">›</view>
      </view>
      <view class="cell link" @tap="go('/pages/settings/data')">
        <view class="cell-label">数据管理（备份 / 恢复）</view><view class="arrow">›</view>
      </view>
    </view>

    <view class="card">
      <view class="section-title">切换模式</view>
      <view class="mode-row">
        <view class="mode-opt" :class="{ active: modeStore.mode === 'shangmen' }" @tap="confirmSwitch('shangmen')">
          <view class="m-title">上门模式</view>
          <view class="m-desc">一对一上门教学</view>
        </view>
        <view class="mode-opt" :class="{ active: modeStore.mode === 'club' }" @tap="confirmSwitch('club')">
          <view class="m-title">俱乐部模式</view>
          <view class="m-desc">场馆班级教学</view>
        </view>
      </view>
      <view class="warn">切换模式将重置本地缓存（备份导出含模式标识，可跨端校验）</view>
    </view>

    <view class="card">
      <view class="cell"><view class="cell-label">版本</view><view class="cell-value">v1.0.0</view></view>
      <view class="cell link danger" @tap="doLogout">
        <view class="cell-label" style="color:#EF4444">退出登录</view><view class="arrow">›</view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { MODES } from '../../utils/constants'
import { useModeStore } from '../../stores/mode'
import { useUserStore } from '../../stores/user'
import { authApi, isLocalMode } from '../../api'

const modeStore = useModeStore()
const userStore = useUserStore()
const user = computed(() => userStore.user)
const modeInfo = computed(() => MODES[modeStore.mode] || MODES.shangmen)
const isLocal = computed(() => isLocalMode())

function go(url) { uni.navigateTo({ url }) }
// 教练入口 → 管理 tab 页教练段（tab 页不支持带参跳转）
function goCoach() {
  uni.setStorageSync('manage_tab', 'coach')
  uni.switchTab({ url: '/pages/manage/manage' })
}

/** 数据来源切换：本地 ↔ 服务器（两套数据各自独立，互不影响；备份可互导） */
function confirmSwitchDataSource() {
  const toLocal = !isLocal.value
  uni.showModal({
    title: '切换数据来源',
    content: toLocal
      ? '将切换到本地模式（数据存本机，无需服务器）。当前服务器数据不会丢失，切换后可随时切回。'
      : '将连接服务器 API（需后端已部署且网络可达）。本地数据不会丢失。切换失败请检查服务器地址。',
    success: (r) => {
      if (!r.confirm) return
      if (toLocal) {
        uni.setStorageSync('authMode', 'local')
        uni.setStorageSync('token', 'local')
        userStore.setUser({ id: 0, phone: '', name: '本地用户', role: 'local' })
      } else {
        uni.setStorageSync('authMode', 'server')
      }
      uni.reLaunch({ url: toLocal ? '/pages/home/home' : '/pages/login/login' })
    },
  })
}

function confirmSwitch(mode) {
  if (mode === modeStore.mode) return
  uni.showModal({
    title: '切换模式',
    content: '将重置本地业务缓存并返回首页，确定切换？',
    success: (r) => {
      if (r.confirm) modeStore.switchMode(mode, true)
    },
  })
}

function doLogout() {
  uni.showModal({
    title: '退出登录', content: '确定退出当前账号？',
    success: async (r) => {
      if (!r.confirm) return
      try { await authApi.logout() } catch (e) { /* 无状态 token，忽略 */ }
      userStore.clear()
      uni.reLaunch({ url: '/pages/login/login' })
    },
  })
}
</script>

<style lang="scss" scoped>
.cell.link .arrow { color: #C0C7D4; font-size: 18px; }
.mode-row { display: flex; gap: 12px; margin-top: 10px;
  .mode-opt { flex: 1; border: 2px solid transparent; border-radius: 12px; padding: 14px; background: #F7F8FC;
    .m-title { font-size: 14px; font-weight: 600; }
    .m-desc { font-size: 11px; color: #8A94A6; margin-top: 4px; }
    &.active { border-color: #5B6BF7; background: #F5F7FF; } } }
.warn { font-size: 11px; color: #F59E0B; margin-top: 10px; }
.danger { .cell-label { color: #EF4444; } }
.avatar-cell { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #8A94A6;
  .mini-avatar { width: 30px; height: 30px; border-radius: 50%; }
  .mini-fallback { width: 30px; height: 30px; border-radius: 50%; background: #5B6BF7; color: #FFF;
    font-size: 14px; font-weight: 600; display: flex; align-items: center; justify-content: center; } }
</style>
