<template>
  <view>
    <!-- 搜索与筛选 -->
    <view class="filter-bar">
      <input class="search" v-model="keyword" placeholder="搜索姓名 / 手机号" confirm-type="search" @confirm="load" />
      <view class="chips">
        <view class="chip" :class="{ active: status === '' }" @tap="setStatus('')">全部</view>
        <view v-for="(s, key) in STUDENT_STATUS" :key="key"
              class="chip" :class="{ active: status === key }" @tap="setStatus(key)">{{ s.label }}</view>
      </view>
    </view>

    <view class="mode-line">当前模式：{{ modeLabel }}</view>

    <student-card v-for="s in list" :key="s.id" :student="s"
                  @tap="go(`/pages/student/detail?id=${s.id}`)" />
    <view v-if="!list.length" class="empty">暂无学员</view>

    <view class="fab" @tap="go('/pages/student/edit')">＋</view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { studentApi } from '../api'
import { STUDENT_STATUS } from '../utils/constants'
import { useModeStore } from '../stores/mode'
import StudentCard from './student-card.vue'

const modeStore = useModeStore()
const modeLabel = modeStore.mode === 'club' ? '俱乐部' : '上门'
const list = ref([])
const keyword = ref('')
const status = ref('')

async function load() {
  const res = await studentApi.list({ keyword: keyword.value, status: status.value, page_size: 200 })
  list.value = res.list
}

function setStatus(s) { status.value = s; load() }
function go(url) { uni.navigateTo({ url }) }

defineExpose({ load })
</script>

<style lang="scss" scoped>
.filter-bar { margin: 12px 16px 0;
  .search { background: #FFF; border-radius: 12px; height: 40px; padding: 0 12px; font-size: 14px; }
  .chips { display: flex; gap: 8px; margin-top: 8px;
    .chip { padding: 5px 14px; border-radius: 16px; background: #FFF; font-size: 12px; color: #5A6478;
      &.active { background: #5B6BF7; color: #FFF; } }
  }
}
.mode-line { font-size: 11px; color: #8A94A6; margin: 8px 16px 0; }
.fab {
  position: fixed; right: 20px; bottom: calc(80px + env(safe-area-inset-bottom));
  width: 52px; height: 52px; border-radius: 50%; background: #5B6BF7; color: #FFF;
  font-size: 26px; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 16px rgba(91, 107, 247, 0.4);
}
</style>
