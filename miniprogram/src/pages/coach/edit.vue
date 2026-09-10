<template>
  <view class="page">
    <view class="card">
      <view class="form-item">
        <text class="form-label">姓名 *</text>
        <input class="form-input" v-model="form.name" placeholder="教练姓名" />
      </view>
      <view class="form-item">
        <text class="form-label">手机号</text>
        <input class="form-input" type="number" v-model="form.phone" maxlength="11" placeholder="选填" />
      </view>
      <view class="form-item">
        <text class="form-label">角色</text>
        <view class="chips">
          <view v-for="(label, key) in COACH_ROLE" :key="key" class="chip"
                :class="{ active: form.role === key }" @tap="form.role = key">{{ label }}</view>
        </view>
      </view>
      <view class="form-item">
        <text class="form-label">状态</text>
        <view class="chips">
          <view v-for="(s, key) in COACH_STATUS" :key="key" class="chip"
                :class="{ active: form.status === key }" @tap="form.status = key">{{ s.label }}</view>
        </view>
      </view>
      <view class="form-item">
        <text class="form-label">薪资模式</text>
        <view class="chips">
          <view v-for="(label, key) in SALARY_MODE" :key="key" class="chip"
                :class="{ active: form.salary_mode === key }" @tap="form.salary_mode = key">{{ label }}</view>
        </view>
      </view>
      <view class="form-item form-row">
        <view style="flex:1">
          <text class="form-label">底薪（元）</text>
          <input class="form-input" type="digit" v-model="form.base_salary" placeholder="0" />
        </view>
        <view >
          <text class="form-label">课时费单价（元）</text>
          <input class="form-input" type="digit" v-model="form.lesson_rate" placeholder="0" />
        </view>
      </view>
      <view class="form-item">
        <text class="form-label">提成比例（%）</text>
        <input class="form-input" type="digit" v-model="form.commission_rate" placeholder="0" />
      </view>
      <view class="form-item">
        <text class="form-label">擅长项目（逗号分隔）</text>
        <input class="form-input" v-model="specialtiesText" placeholder="如：中考体育,体适能" />
      </view>
    </view>

    <view class="btn-primary" :class="{ disabled: saving }" @tap="save">{{ id ? '保存修改' : '新增教练' }}</view>
  </view>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { coachApi } from '../../api'
import { COACH_ROLE, COACH_STATUS, SALARY_MODE } from '../../utils/constants'
import { required, checkPhone } from '../../utils/validator'

const id = ref(0)
const saving = ref(false)
const specialtiesText = ref('')

const form = reactive({
  name: '', phone: '', role: 'parttime', superior_id: null, status: 'active',
  salary_mode: 'per_lesson', base_salary: 0, lesson_rate: 0, commission_rate: 0,
})

async function save() {
  if (saving.value) return
  if (!required(form.name, '姓名')) return
  if (!checkPhone(form.phone)) return
  form.base_salary = Number(form.base_salary) || 0
  form.lesson_rate = Number(form.lesson_rate) || 0
  form.commission_rate = Number(form.commission_rate) || 0
  form.specialties = specialtiesText.value.split(/[,，]/).map(s => s.trim()).filter(Boolean)
  saving.value = true
  try {
    if (id.value) await coachApi.update(id.value, form)
    else await coachApi.create(form)
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 500)
  } finally { saving.value = false }
}

onLoad(async (q) => {
  id.value = Number(q.id || 0)
  if (id.value) {
    const c = await coachApi.detail(id.value)
    Object.assign(form, c)
    specialtiesText.value = Array.isArray(c.specialties) ? c.specialties.join(',') : ''
  }
})
</script>

<style lang="scss" scoped>
.page { padding-bottom: 40px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px;
  .chip { padding: 6px 14px; border-radius: 16px; background: #F7F8FC; font-size: 13px; color: #5A6478;
    &.active { background: #ECF0FF; color: #5B6BF7; font-weight: 600; } } }
.btn-primary { margin: 0 16px; }
</style>
