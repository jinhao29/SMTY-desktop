<template>
  <view>
    <view class="card">
      <view class="section-title">备份导出</view>
      <view class="desc">导出全部业务数据（学员 / 教练 / 排课 / 课时包 / 签到），JSON 含模式标识，可与桌面端 / Android 互相校验。</view>
      <view class="btn-primary" :class="{ disabled: busy }" @tap="doExport">{{ busy ? '处理中...' : '导出并保存' }}</view>
    </view>

    <view class="card">
      <view class="section-title">备份恢复</view>
      <view class="desc">从备份文件导入合并（LWW 语义：仅导入比本地更新的记录）。模式不匹配将被拒绝。</view>
      <view class="btn-secondary" :class="{ disabled: busy }" @tap="doImport">选择备份文件导入</view>
    </view>

    <view class="card">
      <view class="section-title">缓存管理</view>
      <view class="cell">
        <view class="cell-label">当前模式</view>
        <view class="cell-value">{{ modeStore.mode === 'club' ? '俱乐部' : '上门' }}</view>
      </view>
      <view class="cell link" @tap="clearCache">
        <view class="cell-label">清理本地缓存（保留登录态）</view><view class="arrow">›</view>
      </view>
    </view>

    <view class="log card" v-if="log">
      <view class="section-title">最近操作结果</view>
      <text class="log-text">{{ log }}</text>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { backupApi } from '../../api'
import { useModeStore } from '../../stores/mode'
import { BASE_URL } from '../../utils/request'

const modeStore = useModeStore()
const busy = ref(false)
const log = ref('')

async function doExport() {
  if (busy.value) return
  busy.value = true
  try {
    const data = await backupApi.exportData()
    // #ifdef H5
    downloadJson(data)
    // #endif
    // #ifndef H5
    const path = `${uni.env.USER_DATA_PATH}/backup_${Date.now()}.json`
    const fs = uni.getFileSystemManager()
    fs.writeFileSync(path, JSON.stringify(data), 'utf8')
    uni.shareFileMessage && uni.shareFileMessage({ filePath: path, fileName: `backup_${data.mode}_${data.exported_at.slice(0, 10)}.json` })
    log.value = `已导出 ${Object.keys(data).filter(k => Array.isArray(data[k])).map(k => `${k}:${data[k].length}`).join(' ')}`
    // #endif
  } finally { busy.value = false }
}

/** H5 调试时浏览器下载 */
function downloadJson(data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `backup_${data.mode}_${data.exported_at.slice(0, 10)}.json`
  a.click()
  log.value = '已触发浏览器下载'
}

function doImport() {
  // #ifdef H5
  pickAndUpload()
  return
  // #endif
  // #ifndef H5
  uni.chooseMessageFile({
    count: 1, type: 'file', extension: ['json'],
    success: async (res) => {
      const fs = uni.getFileSystemManager()
      const text = fs.readFileSync(res.tempFiles[0].path, 'utf8')
      await importPayload(text)
    },
  })
  // #endif
}

/** H5 调试：file input 选择文件后直接 POST 到后端 */
function pickAndUpload() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async () => {
    const text = await input.files[0].text()
    await importPayload(text)
  }
  input.click()
}

async function importPayload(text) {
  let data
  try { data = JSON.parse(text) } catch { return uni.showToast({ title: '文件格式错误', icon: 'none' }) }
  uni.showModal({
    title: '确认恢复',
    content: `备份模式：${data.mode}，将按 LWW 合并导入。继续？`,
    success: async (r) => {
      if (!r.confirm) return
      const res = await backupApi.importData(data)
      log.value = `导入完成：${Object.entries(res.imported).map(([k, v]) => `${k}:${v}`).join(' ')}`
      uni.showToast({ title: '恢复成功', icon: 'success' })
    },
  })
}

function clearCache() {
  uni.showModal({
    title: '清理缓存', content: '将清除本地业务缓存（保留登录态与模式设置），确定？',
    success: (r) => {
      if (!r.confirm) return
      const keep = { token: uni.getStorageSync('token'), mode: uni.getStorageSync('mode'), user: uni.getStorageSync('user') }
      uni.clearStorageSync()
      Object.entries(keep).forEach(([k, v]) => { if (v) uni.setStorageSync(k, v) })
      uni.showToast({ title: '已清理', icon: 'success' })
    },
  })
}
</script>

<style lang="scss" scoped>
.desc { font-size: 12px; color: #8A94A6; margin: 8px 0 14px; line-height: 1.6; }
.btn-secondary { border: 1px solid #5B6BF7; color: #5B6BF7; }
.cell.link .arrow { color: #C0C7D4; font-size: 18px; }
.log { .log-text { font-size: 12px; color: #5A6478; line-height: 1.8; word-break: break-all; } }
</style>
