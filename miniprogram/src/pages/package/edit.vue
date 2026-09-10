<template>
  <view class="page">
    <view class="card">
      <view class="form-item">
        <text class="form-label">学员 *</text>
        <picker :range="studentOptions" range-key="label" @change="(e) => form.student_id = studentOptions[e.detail.value].id">
          <view class="form-input picker">{{ studentName || '请选择学员' }}</view>
        </picker>
      </view>
      <view class="form-item">
        <text class="form-label">名称 *</text>
        <input class="form-input" v-model="form.name" placeholder="如：20课时基础包" />
      </view>
      <view class="form-item">
        <text class="form-label">总课时 *</text>
        <input class="form-input" type="number" v-model="form.total_lessons" placeholder="如：20" />
      </view>
      <view class="form-item">
        <text class="form-label">价格（元）</text>
        <input class="form-input" type="digit" v-model="form.price" placeholder="0" />
      </view>
      <view class="form-item">
        <text class="form-label">实收金额（-1 表示已付清）</text>
        <input class="form-input" type="digit" v-model="form.paid_amount" placeholder="-1 或具体金额" />
      </view>
      <view class="form-item">
        <text class="form-label">有效期至</text>
        <picker mode="date" :value="form.expire_date" @change="(e) => form.expire_date = e.detail.value">
          <view class="form-input picker">{{ form.expire_date || '不限' }}</view>
        </picker>
      </view>
      <view class="form-item">
        <text class="form-label">购买日期</text>
        <picker mode="date" :value="form.purchase_date" @change="(e) => form.purchase_date = e.detail.value">
          <view class="form-input picker">{{ form.purchase_date }}</view>
        </picker>
      </view>
    </view>

    <view class="btn-primary" :class="{ disabled: saving }" @tap="save">{{ id ? '保存修改' : '新增课时包' }}</view>
  </view>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { packageApi, studentApi } from '../../api'
import { required, checkNumber } from '../../utils/validator'

const id = ref(0)
const saving = ref(false)
const students = ref([])

const form = reactive({
  student_id: null, name: '', total_lessons: '', price: 0,
  paid_amount: -1, expire_date: '', purchase_date: '',
})

const studentOptions = computed(() => students.value.map(s => ({ id: s.id, label: s.name })))
const studentName = computed(() => studentOptions.value.find(s => s.id === form.student_id)?.label || '')

async function save() {
  if (saving.value) return
  if (!form.student_id) { uni.showToast({ title: '请选择学员', icon: 'none' }); return }
  if (!required(form.name, '名称')) return
  if (!checkNumber(form.total_lessons, '总课时', 1)) return
  form.total_lessons = Number(form.total_lessons)
  form.price = Number(form.price) || 0
  form.paid_amount = form.paid_amount === '' ? -1 : Number(form.paid_amount)
  saving.value = true
  try {
    if (id.value) await packageApi.update(id.value, form)
    else await packageApi.create(form)
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 500)
  } finally { saving.value = false }
}

onLoad(async (q) => {
  id.value = Number(q.id || 0)
  const s = await studentApi.list({ page_size: 200 })
  students.value = s.list
  if (id.value) {
    const p = await packageApi.detail(id.value)
    Object.assign(form, p)
  }
})
</script>

<style lang="scss" scoped>
.page { padding-bottom: 40px; }
.picker { line-height: 44px; }
.btn-primary { margin: 0 16px; }
</style>
