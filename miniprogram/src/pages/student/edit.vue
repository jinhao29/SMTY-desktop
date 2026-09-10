<template>
  <view class="page">
    <view class="card">
      <view class="form-item">
        <text class="form-label">姓名 *</text>
        <input class="form-input" v-model="form.name" placeholder="学员姓名" />
      </view>
      <view class="form-item">
        <text class="form-label">手机号</text>
        <input class="form-input" type="number" v-model="form.phone" maxlength="11" placeholder="选填" />
      </view>
      <view class="form-item">
        <text class="form-label">年级</text>
        <input class="form-input" v-model="form.grade" placeholder="如：三年级 / 初一" />
      </view>
      <view class="form-item">
        <text class="form-label">家长联系方式</text>
        <input class="form-input" type="number" v-model="form.parent_phone" maxlength="11" placeholder="选填" />
      </view>
      <view class="form-item">
        <text class="form-label">{{ isClub ? '上课场馆' : '小区地址' }}</text>
        <input class="form-input" v-model="form.address" :placeholder="isClub ? '如：大学城体育中心' : '如：某小区某栋'" />
      </view>
      <view v-if="isClub" class="form-item">
        <text class="form-label">班级</text>
        <view class="chips">
          <view v-for="g in CLASS_GROUPS" :key="g" class="chip"
                :class="{ active: form.class_group === g }" @tap="form.class_group = g">{{ g }}</view>
        </view>
      </view>
      <view class="form-item">
        <text class="form-label">状态</text>
        <view class="chips">
          <view v-for="(s, key) in STUDENT_STATUS" :key="key" class="chip"
                :class="{ active: form.status === key }" @tap="form.status = key">{{ s.label }}</view>
        </view>
      </view>
      <view class="form-item">
        <text class="form-label">课时到期日</text>
        <picker mode="date" :value="form.expire_date" @change="(e) => form.expire_date = e.detail.value">
          <view class="form-input picker">{{ form.expire_date || '选填' }}</view>
        </picker>
      </view>
      <view class="form-item">
        <text class="form-label">备注</text>
        <textarea class="form-textarea" v-model="form.note" placeholder="选填" />
      </view>
    </view>

    <view class="btn-primary" :class="{ disabled: saving }" @tap="save">{{ id ? '保存修改' : '新增学员' }}</view>
  </view>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { studentApi } from '../../api'
import { STUDENT_STATUS, CLASS_GROUPS } from '../../utils/constants'
import { required, checkPhone } from '../../utils/validator'
import { useModeStore } from '../../stores/mode'

const modeStore = useModeStore()
const isClub = computed(() => modeStore.mode === 'club')
const id = ref(0)
const saving = ref(false)

const form = reactive({
  name: '', phone: '', grade: '', parent_phone: '',
  address: '', class_group: '', status: 'active', expire_date: '', note: '',
})

async function save() {
  if (saving.value) return
  if (!required(form.name, '姓名')) return
  if (!checkPhone(form.phone)) return
  if (!checkPhone(form.parent_phone, '家长手机号')) return
  saving.value = true
  try {
    if (id.value) await studentApi.update(id.value, form)
    else await studentApi.create(form)
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 500)
  } finally { saving.value = false }
}

onLoad(async (q) => {
  id.value = Number(q.id || 0)
  if (id.value) {
    const s = await studentApi.detail(id.value)
    Object.assign(form, s)
  }
})
</script>

<style lang="scss" scoped>
.page { padding-bottom: 40px; }
.picker { line-height: 44px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px;
  .chip { padding: 6px 14px; border-radius: 16px; background: #F7F8FC; font-size: 13px; color: #5A6478;
    &.active { background: #ECF0FF; color: #5B6BF7; font-weight: 600; } }
}
.btn-primary { margin: 0 16px; }
</style>
