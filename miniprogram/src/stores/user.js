import { defineStore } from 'pinia'
import { pickAvatar } from '../utils/avatar'

/** 用户状态（含头像；跳过登录时默认显示「李」） */
export const useUserStore = defineStore('user', {
  state: () => ({
    user: uni.getStorageSync('user') || null,
    avatar: uni.getStorageSync('avatar') || '',
  }),
  getters: {
    /** 显示名：登录用户取 name/phone，本地模式兜底「李」 */
    displayName: (s) => s.user?.name || s.user?.phone || '李',
  },
  actions: {
    setUser(u) {
      this.user = u
      uni.setStorageSync('user', u)
    },
    async changeAvatar() {
      try {
        const b64 = await pickAvatar()
        this.avatar = b64
        uni.setStorageSync('avatar', b64)
        uni.showToast({ title: '头像已更新', icon: 'success' })
      } catch (e) { /* 用户取消选图，静默 */ }
    },
    clear() {
      this.user = null
      uni.removeStorageSync('user')
      uni.removeStorageSync('token')
    },
  },
})
