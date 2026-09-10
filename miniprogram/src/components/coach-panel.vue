<template>
  <view>
    <!-- 统计 -->
    <view class="stats card">
      <view class="stat-item"><view class="v">{{ stats.total }}</view><view class="l">总教练</view></view>
      <view class="stat-item"><view class="v">{{ stats.fulltime }}</view><view class="l">全职</view></view>
      <view class="stat-item"><view class="v">{{ stats.parttime }}</view><view class="l">兼职</view></view>
      <view class="stat-item"><view class="v">{{ stats.partner_level1 + stats.partner_level2 }}</view><view class="l">合伙人</view></view>
    </view>

    <!-- 筛选 -->
    <view class="filter-bar">
      <input class="search" v-model="keyword" placeholder="搜索姓名 / 手机号" confirm-type="search" @confirm="load" />
      <view class="chips">
        <view class="chip" :class="{ active: role === '' }" @tap="setRole('')">全部</view>
        <view v-for="(label, key) in COACH_ROLE" :key="key" class="chip"
              :class="{ active: role === key }" @tap="setRole(key)">{{ label }}</view>
      </view>
    </view>

    <coach-card v-for="c in list" :key="c.id" :coach="c"
                @tap="go(`/pages/coach/detail?id=${c.id}`)" />
    <view v-if="!list.length" class="empty">暂无教练</view>

    <view class="fab" @tap="go('/pages/coach/edit')">＋</view>
  </view>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { coachApi } from '../api'
import { COACH_ROLE } from '../utils/constants'
import CoachCard from './coach-card.vue'

const list = ref([])
const stats = reactive({ total: 0, fulltime: 0, parttime: 0, partner_level1: 0, partner_level2: 0 })
const keyword = ref('')
const role = ref('')

async function load() {
  const res = await coachApi.list({ keyword: keyword.value, role: role.value, page_size: 100 })
  list.value = res.list
  Object.assign(stats, res.stats)
}

function setRole(r) { role.value = r; load() }
function go(url) { uni.navigateTo({ url }) }

defineExpose({ load })
</script>

<style lang="scss" scoped>
.stats { display: flex; text-align: center; padding: 14px 0;
  .stat-item { flex: 1;
    .v { font-size: 20px; font-weight: 700; color: #1A2233; }
    .l { font-size: 11px; color: #8A94A6; margin-top: 2px; } }
}
.filter-bar { margin: 12px 16px 0;
  .search { background: #FFF; border-radius: 12px; height: 40px; padding: 0 12px; font-size: 14px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px;
    .chip { padding: 5px 12px; border-radius: 16px; background: #FFF; font-size: 12px; color: #5A6478;
      &.active { background: #5B6BF7; color: #FFF; } } }
}
.fab {
  position: fixed; right: 20px; bottom: calc(80px + env(safe-area-inset-bottom));
  width: 52px; height: 52px; border-radius: 50%; background: #5B6BF7; color: #FFF;
  font-size: 26px; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 16px rgba(91, 107, 247, 0.4);
}
</style>
