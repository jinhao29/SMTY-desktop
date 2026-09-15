<template>
  <view class="tab-page">
    <!-- 自定义导航栏：头像 + 标题（原生栏放不了自定义组件） -->
    <view class="nav" :style="{ paddingTop: statusBarH + 'px' }">
      <view class="nav-inner">
        <view class="nav-side" @tap="userStore.changeAvatar()">
          <image v-if="userStore.avatar" :src="userStore.avatar" class="nav-avatar-img" />
          <view v-else class="nav-avatar-fallback">{{ userStore.displayName.charAt(0) }}</view>
        </view>
        <view class="nav-title">首页</view>
        <view class="nav-side" />
      </view>
    </view>
    <!-- 今日概览（内联结构：组件标签在微信端不参与 flex 分配，flex:1 必须落在真实 view 上） -->
    <view class="overview">
      <view class="ov-card"><view class="ov-value" style="color:#5B6BF7">{{ data.lesson_count }}</view><view class="ov-label">今日排课</view></view>
      <view class="ov-card"><view class="ov-value" style="color:#34C77B">{{ data.signed_count }}</view><view class="ov-label">已签到</view></view>
      <view class="ov-card"><view class="ov-value" style="color:#F59E0B">{{ data.pending_count }}</view><view class="ov-label">未签到</view></view>
      <view class="ov-card"><view class="ov-value" style="color:#8A94A6">{{ data.student_count }}</view><view class="ov-label">总学员</view></view>
    </view>

    <!-- 快捷入口 -->
    <view class="quick card">
      <view class="quick-item" @tap="go('/pages/checkin/index')">
        <image class="q-icon" src="/static/icons/quick-checkin.png" />
        <view class="q-label">签到</view>
      </view>
      <view class="quick-item" @tap="go('/pages/schedule/lesson-edit')">
        <image class="q-icon" src="/static/icons/quick-lesson.png" />
        <view class="q-label">排课</view>
      </view>
      <view class="quick-item" @tap="goManage('student')">
        <image class="q-icon" src="/static/icons/quick-student.png" />
        <view class="q-label">学员</view>
      </view>
      <view class="quick-item" @tap="goManage('coach')">
        <image class="q-icon" src="/static/icons/quick-coach.png" />
        <view class="q-label">教练</view>
      </view>
    </view>

    <!-- 续费提醒（纯查询；阈值与 Android RenewalThresholds 同源：剩余≤3 / 30 天内到期） -->
    <view class="card renew" v-if="renewal.count">
      <view class="head-row">
        <view class="section-title" style="color:#F59E0B">⏰ 续费提醒（{{ renewal.count }}）</view>
        <view class="link" @tap="go('/pages/package/list')">全部课时包 ›</view>
      </view>
      <view v-for="a in renewal.list.slice(0, 5)" :key="a.package_id"
            class="renew-row" @tap="goStudent(a.student_id)">
        <text class="r-name">{{ a.student_name }}</text>
        <text class="r-reason">{{ a.reason }}</text>
        <text class="r-sub">剩 {{ a.remaining_lessons }} 节{{ renewWhen(a) }}</text>
      </view>
      <view v-if="renewal.count > 5" class="more" @tap="go('/pages/package/list')">
        还有 {{ renewal.count - 5 }} 条 ›
      </view>
    </view>

    <!-- 今日课程 -->
    <view class="card">
      <view class="section-title">今日课程</view>
      <view v-if="!data.lessons.length" class="empty">今天暂无排课</view>
      <lesson-card v-for="l in data.lessons" :key="l.id" :lesson="l" @tap="goDetail(l)" />
    </view>
  </view>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { onPullDownRefresh, onShow } from '@dcloudio/uni-app'
import { lessonApi, packageApi } from '../../api'
import { useUserStore } from '../../stores/user'
import LessonCard from '../../components/lesson-card.vue'

const userStore = useUserStore()
// 自定义导航栏：状态栏高度（H5 为 0）
const statusBarH = ref(0)
// #ifdef MP-WEIXIN
statusBarH.value = uni.getWindowInfo().statusBarHeight || 0
// #endif

const data = reactive({ lesson_count: 0, signed_count: 0, pending_count: 0, student_count: 0, lessons: [] })
const renewal = ref({ count: 0, list: [] })

async function load() {
  const res = await lessonApi.today()
  Object.assign(data, res)
  try {
    renewal.value = await packageApi.renewalAlerts()
  } catch (e) { renewal.value = { count: 0, list: [] } }
}

function renewWhen(a) {
  if (a.reason === '即将过期') return ` · ${a.days_to_expire} 天后到期`
  if (a.reason === '已过期') return ' · 已过期'
  return a.expire_date ? ` · ${a.expire_date.slice(5)} 到期` : ''
}

onMounted(load)
onShow(load)
onPullDownRefresh(async () => {
  await load()
  uni.stopPullDownRefresh()
})

function go(url) { uni.navigateTo({ url }) }
function goStudent(id) { uni.navigateTo({ url: `/pages/student/detail?id=${id}` }) }
// 快捷入口跳管理页并定位分段（tab 页不支持带参跳转，用 storage 传递）
function goManage(seg) {
  uni.setStorageSync('manage_tab', seg)
  uni.switchTab({ url: '/pages/manage/manage' })
}
function goDetail(l) { uni.navigateTo({ url: `/pages/checkin/index?lessonId=${l.id}` }) }
</script>

<style lang="scss" scoped>
/* 自定义导航栏：头像左 / 标题中 */
.nav { background: transparent;
  .nav-inner { height: 44px; display: flex; align-items: center; padding: 0 16px; }
  .nav-side { width: 34px; height: 34px; flex: 0 0 34px; }
  .nav-avatar-img { width: 34px; height: 34px; border-radius: 50%; display: block; }
  .nav-avatar-fallback { width: 34px; height: 34px; border-radius: 50%; background: #5B6BF7; color: #FFF;
    font-size: 16px; font-weight: 600; display: flex; align-items: center; justify-content: center; }
  .nav-title { flex: 1; text-align: center; font-size: 17px; font-weight: 600; color: #1A1F2E; }
}
.overview { display: flex; gap: 8px; margin: 12px 16px 0;
  .ov-card {
    flex: 1; min-width: 0; background: #FFFFFF; border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); padding: 14px 4px; text-align: center;
    .ov-value { font-size: 20px; font-weight: 700; }
    .ov-label { font-size: 11px; color: #8A94A6; margin-top: 4px; }
  }
}
.quick { display: flex; justify-content: space-around;
  .quick-item { text-align: center;
    .q-icon { width: 44px; height: 44px; margin: 0 auto; display: block; }
    .q-label { font-size: 12px; color: #5A6478; margin-top: 6px; }
  }
}
.renew { border-left: 3px solid #F59E0B;
  .head-row { display: flex; justify-content: space-between; align-items: center;
    .link { font-size: 12px; color: #5B6BF7; } }
  .renew-row { display: flex; align-items: center; gap: 8px; padding: 7px 0;
    border-top: 1px solid #F0F2F7;
    &:first-of-type { border-top: none; }
    .r-name { font-size: 14px; font-weight: 600; }
    .r-reason { font-size: 11px; color: #F59E0B; font-weight: 600; }
    .r-sub { font-size: 11px; color: #8A94A6; margin-left: auto; } }
  .more { font-size: 12px; color: #5B6BF7; padding-top: 6px; border-top: 1px solid #F0F2F7; }
}
.section-title { margin-bottom: 8px; }
</style>
