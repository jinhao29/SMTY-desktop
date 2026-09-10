<template>
  <view v-if="s">
    <!-- 基本信息卡 -->
    <view class="card">
      <view class="head">
        <view class="avatar">{{ s.name.slice(0, 1) }}</view>
        <view class="head-info">
          <view class="name-row">
            <text class="name">{{ s.name }}</text>
            <text class="tag" :class="'tag-' + statusInfo.type">{{ statusInfo.label }}</text>
            <text v-if="s.class_group" class="tag">{{ s.class_group }}</text>
          </view>
          <view class="sub">{{ s.grade || '未填年级' }}</view>
        </view>
        <view class="remain">
          <view class="num">{{ s.remaining_lessons }}</view>
          <view class="unit">剩余课时</view>
        </view>
      </view>
      <view class="cell"><view class="cell-label">手机号</view><view class="cell-value">{{ s.phone || '—' }}</view></view>
      <view class="cell"><view class="cell-label">家长联系方式</view><view class="cell-value">{{ s.parent_phone || '—' }}</view></view>
      <view class="cell"><view class="cell-label">{{ modeStore.mode === 'club' ? '上课场馆' : '小区地址' }}</view><view class="cell-value">{{ s.address || '—' }}</view></view>
      <view class="cell"><view class="cell-label">课时到期日</view><view class="cell-value">{{ s.expire_date || '—' }}</view></view>
      <view class="cell" v-if="s.note"><view class="cell-label">备注</view><view class="cell-value">{{ s.note }}</view></view>
    </view>

    <!-- 课时记录 -->
    <view class="card">
      <view class="section-title">课时记录</view>
      <view v-if="!lessons.packages.length" class="empty">暂无课时包</view>
      <view v-for="p in lessons.packages" :key="p.id" class="pkg-row">
        <view>
          <view class="pkg-name">{{ p.name }}</view>
          <view class="pkg-sub">{{ p.purchase_date }} 购入 · ¥{{ p.price }}</view>
        </view>
        <view class="pkg-right">
          <text class="pkg-remain">{{ p.remaining_lessons }}</text>
          <text class="pkg-total">/{{ p.total_lessons }}</text>
        </view>
      </view>
    </view>

    <!-- 签到历史 -->
    <view class="card">
      <view class="section-title">最近签到</view>
      <view v-if="!lessons.checkins.length" class="empty">暂无签到记录</view>
      <view v-for="c in lessons.checkins.slice(0, 10)" :key="c.id" class="cell">
        <view class="cell-label">{{ c.timestamp }}</view>
        <view class="cell-value">{{ c.type === 'check_in' ? '签到' : '签退' }}</view>
      </view>
    </view>

    <view class="edit-btn" @tap="goEdit">编辑资料</view>
  </view>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { studentApi } from '../../api'
import { STUDENT_STATUS } from '../../utils/constants'
import { useModeStore } from '../../stores/mode'

const uni = globalThis.uni
const modeStore = useModeStore()
const s = ref(null)
const lessons = reactive({ packages: [], checkins: [], lessons: [] })
const id = ref(0)
const statusInfo = computed(() => s.value ? (STUDENT_STATUS[s.value.status] || { label: s.value.status, type: 'gray' }) : {})

async function load() {
  s.value = await studentApi.detail(id.value)
  const res = await studentApi.lessons(id.value)
  Object.assign(lessons, res)
}

onLoad((q) => { id.value = Number(q.id) })
onShow(load)

function goEdit() { uni.navigateTo({ url: `/pages/student/edit?id=${id.value}` }) }
</script>

<style lang="scss" scoped>
.head { display: flex; align-items: center; margin-bottom: 8px;
  .avatar { width: 52px; height: 52px; border-radius: 50%; background: #ECF0FF; color: #5B6BF7;
    font-size: 20px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
  .head-info { flex: 1; margin-left: 12px;
    .name-row { display: flex; align-items: center; gap: 6px; }
    .name { font-size: 18px; font-weight: 700; }
    .sub { font-size: 12px; color: #8A94A6; margin-top: 4px; } }
  .remain { text-align: center;
    .num { font-size: 22px; font-weight: 700; color: #5B6BF7; }
    .unit { font-size: 10px; color: #8A94A6; } }
}
.pkg-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0;
  border-bottom: 1px solid #F0F2F7;
  &:last-child { border-bottom: none; }
  .pkg-name { font-size: 14px; font-weight: 600; }
  .pkg-sub { font-size: 11px; color: #8A94A6; margin-top: 2px; }
  .pkg-remain { font-size: 16px; font-weight: 700; color: #5B6BF7; }
  .pkg-total { font-size: 12px; color: #8A94A6; }
}
.edit-btn {
  margin: 8px 16px 32px; text-align: center; line-height: 44px; height: 44px;
  background: #FFF; border: 1px solid #5B6BF7; color: #5B6BF7; border-radius: 12px; font-size: 15px;
}
</style>
