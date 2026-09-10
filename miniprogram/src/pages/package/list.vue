<template>
  <view>
    <!-- 统计卡片 -->
    <view class="ov card">
      <view class="ov-row1">
        <view class="ov-item"><view class="v">{{ stats.total_lessons }}</view><view class="l">总课时</view></view>
        <view class="ov-item"><view class="v">{{ stats.consumed_lessons }}</view><view class="l">已消</view></view>
        <view class="ov-item"><view class="v" style="color:#5B6BF7">{{ stats.remaining_lessons }}</view><view class="l">剩余</view></view>
        <view class="ov-item"><view class="v">{{ stats.student_count }}</view><view class="l">总学员</view></view>
      </view>
      <view class="ov-fees">
        <view class="fee-item">
          <view class="f-label">总应收</view>
          <view class="f-value">¥{{ stats.total_receivable }}</view>
        </view>
        <view class="fee-item">
          <view class="f-label">实收</view>
          <view class="f-value" style="color:#34C77B">¥{{ stats.total_received }}</view>
        </view>
        <view class="fee-item">
          <view class="f-label">待收</view>
          <view class="f-value" style="color:#F59E0B">¥{{ stats.total_pending }}</view>
        </view>
      </view>
    </view>

    <!-- 课时包列表 -->
    <view class="card">
      <view class="head-row">
        <view class="section-title">课时包</view>
        <view class="link" @tap="() => {}">—</view>
      </view>
      <view v-if="!list.length" class="empty">暂无课时包</view>
      <view v-for="p in list" :key="p.id" class="pkg" @tap="goEdit(p.id)">
        <view class="pkg-info">
          <view class="pkg-name">{{ p.name }} <text class="tag tag-gray">{{ p.student_name }}</text></view>
          <view class="pkg-sub">购于 {{ p.purchase_date }} · 到期 {{ p.expire_date || '不限' }} · ¥{{ p.price }}</view>
        </view>
        <view class="pkg-right">
          <view class="pkg-remain">{{ p.remaining_lessons }}<text class="pkg-total">/{{ p.total_lessons }}</text></view>
          <text class="tag" :class="'tag-' + (stInfo(p.status).type === 'default' ? 'gray' : stInfo(p.status).type)">{{ stInfo(p.status).label }}</text>
        </view>
      </view>
    </view>

    <view class="fab" @tap="goEdit(0)">＋</view>
  </view>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { packageApi } from '../../api'
import { PACKAGE_STATUS } from '../../utils/constants'

const stats = reactive({ total_lessons: 0, consumed_lessons: 0, remaining_lessons: 0,
  student_count: 0, total_receivable: 0, total_received: 0, total_pending: 0 })
const list = ref([])

const stInfo = (s) => PACKAGE_STATUS[s] || { label: s, type: 'gray' }

async function load() {
  const res = await packageApi.list()
  Object.assign(stats, res.stats)
  stats.student_count = new Set(res.list.map(p => p.student_id)).size
  list.value = res.list
}

function goEdit(id) { uni.navigateTo({ url: `/pages/package/edit?id=${id}` }) }

onShow(load)
</script>

<style lang="scss" scoped>
.ov { padding: 16px;
  .ov-row1 { display: flex; text-align: center;
    .ov-item { flex: 1;
      .v { font-size: 20px; font-weight: 700; }
      .l { font-size: 11px; color: #8A94A6; margin-top: 2px; } } }
  .ov-fees { display: flex; margin-top: 14px; padding-top: 12px; border-top: 1px solid #F0F2F7;
    .fee-item { flex: 1; text-align: center;
      .f-label { font-size: 11px; color: #8A94A6; }
      .f-value { font-size: 15px; font-weight: 700; margin-top: 4px; } } }
}
.head-row { display: flex; justify-content: space-between; margin-bottom: 8px; }
.pkg { display: flex; align-items: center; justify-content: space-between; padding: 12px 0;
  border-bottom: 1px solid #F0F2F7;
  &:last-child { border-bottom: none; }
  .pkg-name { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
  .pkg-sub { font-size: 11px; color: #8A94A6; margin-top: 3px; }
  .pkg-remain { font-size: 17px; font-weight: 700; color: #5B6BF7; text-align: right; }
  .pkg-total { font-size: 11px; color: #8A94A6; font-weight: 400; } }
.fab {
  position: fixed; right: 20px; bottom: calc(40px + env(safe-area-inset-bottom));
  width: 52px; height: 52px; border-radius: 50%; background: #5B6BF7; color: #FFF;
  font-size: 26px; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 16px rgba(91, 107, 247, 0.4);
}
</style>
