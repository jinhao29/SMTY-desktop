<template>
  <view class="login">
    <view class="title">登录</view>
    <view class="subtitle">使用教练账号登录（复用桌面端账号体系）</view>
    <view class="form-item">
      <text class="form-label">手机号</text>
      <input class="form-input" type="number" v-model="phone" maxlength="11" placeholder="请输入手机号" />
    </view>
    <view class="form-item">
      <text class="form-label">密码</text>
      <input class="form-input" password v-model="password" placeholder="请输入密码" />
    </view>
    <view class="btn-primary" :class="{ disabled: loading }" @tap="doLogin">
      {{ loading ? '登录中...' : '登录' }}
    </view>
    <view class="divider"><text>或</text></view>
    <view class="skip-btn" :class="{ disabled: loading }" @tap="skipLogin">跳过登录，进入本地模式</view>
    <view class="tip">本地模式：数据保存在本机，无需服务器，随时可在「数据管理」备份导出</view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { authApi } from '../../api'
import { useUserStore } from '../../stores/user'
import { required, checkPhone } from '../../utils/validator'

const userStore = useUserStore()
const phone = ref('')
const password = ref('')
const loading = ref(false)

function enter(res) {
  uni.setStorageSync('token', res.token)
  userStore.setUser(res.user)
  uni.reLaunch({ url: '/pages/home/home' })
}

async function doLogin() {
  if (loading.value) return
  if (!checkPhone(phone.value, '手机号', false)) return
  if (!required(password.value, '密码')) return
  loading.value = true
  uni.setStorageSync('authMode', 'server')
  try {
    const res = await authApi.login(phone.value.trim(), password.value)
    enter(res)
  } catch (e) {
    // 失败时回落本地模式标记，避免残留 server 态
    uni.removeStorageSync('authMode')
  } finally {
    loading.value = false
  }
}

function skipLogin() {
  if (loading.value) return
  uni.setStorageSync('authMode', 'local')
  uni.setStorageSync('token', 'local')
  userStore.setUser({ id: 0, phone: '', name: '李', role: 'local' })
  uni.reLaunch({ url: '/pages/home/home' })
}
</script>

<style lang="scss" scoped>
.login { min-height: 100vh; background: #FFF; padding: 80px 32px; }
.title { font-size: 26px; font-weight: 700; }
.subtitle { font-size: 13px; color: #8A94A6; margin: 8px 0 40px; }
.divider {
  display: flex; align-items: center; margin: 28px 0;
  &::before, &::after { content: ''; flex: 1; height: 1px; background: #F0F2F7; }
  text { font-size: 12px; color: #C0C7D4; padding: 0 14px; }
}
.skip-btn {
  text-align: center; line-height: 44px; height: 44px;
  background: #F5F7FF; color: #5B6BF7; border-radius: 12px; font-size: 15px; font-weight: 600;
}
.tip { text-align: center; font-size: 12px; color: #C0C7D4; margin-top: 24px; line-height: 1.6; }
</style>
