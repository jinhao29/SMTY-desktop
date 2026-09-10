<template>
  <view>
    <view class="filter-bar">
      <picker mode="date" :value="date" @change="(e) => { date = e.detail.value; load() }">
        <view class="date-pick">{{ date || '全部日期' }} ▾</view>
      </picker>
      <view class="chips">
        <view class="chip" :class="{ active: type === '' }" @tap="setType('')">全部</view>
        <view class="chip" :class="{ active: type === 'check_in' }" @tap="setType('check_in')">签到</view>
        <view class="chip" :class="{ active: type === 'check_out' }" @tap="setType('check_out')">签退</view>
      </view>
    </view>

    <view class="card">
      <view v-if="!list.length" class="empty">暂无记录</view>
      <view v-for="r in list" :key="r.id" class="cell">
        <view>
          <view class="r-name">{{ r.student_name }}</view>
          <view class="r-sub">{{ r.timestamp }}</view>
        </view>
        <view class="tag" :class="r.type === 'check_in' ? 'tag-success' : 'tag-gray'">
          {{ r.type === 'check_in' ? '签到' : '签退' }}
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { checkinApi } from '../../api'

const list = ref([])
const date = ref('')
const type = ref('')

async function load() {
  const res = await checkinApi.history({ date: date.value, type: type.value })
  list.value = res.list
}

function setType(t) { type.value = t; load() }

onShow(load)
</script>

<style lang="scss" scoped>
.filter-bar { display: flex; align-items: center; justify-content: space-between; margin: 12px 16px;
  .date-pick { font-size: 14px; font-weight: 600; }
  .chips { display: flex; gap: 8px;
    .chip { padding: 5px 12px; border-radius: 16px; background: #FFF; font-size: 12px; color: #5A6478;
      &.active { background: #5B6BF7; color: #FFF; } } }
}
.r-name { font-size: 14px; font-weight: 600; }
.r-sub { font-size: 11px; color: #8A94A6; margin-top: 2px; }
</style>
