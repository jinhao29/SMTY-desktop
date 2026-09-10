<template>
  <view class="stat-card">
    <view class="stat-value" :style="{ color }">{{ value }}</view>
    <view class="stat-label">{{ label }}</view>
  </view>
</template>

<script setup>
// 微信端虚拟节点：让组件根的 flex:1 真正参与父级 flex 分配
defineOptions({ virtualHost: true })

defineProps({
  label: String,
  value: [String, Number],
  color: { type: String, default: '#5B6BF7' },
})
</script>

<style lang="scss" scoped>
.stat-card {
  flex: 1;
  background: #FFFFFF;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 14px 8px;
  text-align: center;

  .stat-value { font-size: 20px; font-weight: 700; }
  .stat-label { font-size: 12px; color: #8A94A6; margin-top: 4px; }
}
</style>
