import { defineStore } from 'pinia'

/** 模式状态：上门 / 俱乐部 */
export const useModeStore = defineStore('mode', {
  state: () => ({
    mode: uni.getStorageSync('mode') || 'shangmen',
  }),
  actions: {
    setMode(mode) {
      this.mode = mode
      uni.setStorageSync('mode', mode)
    },
    /** 切换模式：业务数据按模式后缀隔离（local-store / 后端分库），此处无需清缓存 */
    switchMode(mode) {
      this.setMode(mode)
      uni.reLaunch({ url: '/pages/home/home' })
    },
  },
})
