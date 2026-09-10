<script>
export default {
  onLaunch() {
    // 首次启动：若无 token 则进入登录页，否则进入首页
    const token = uni.getStorageSync('token')
    if (!token) {
      uni.reLaunch({ url: '/pages/login/login' })
    }
  },
}
</script>

<style lang="scss">
@import './styles/common.scss';

page {
  background-color: #F2F4F8;
  color: #1A2233;
  font-size: 14px;
  font-family: -apple-system, 'PingFang SC', 'Helvetica Neue', sans-serif;
}
</style>
