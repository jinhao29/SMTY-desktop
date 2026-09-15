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
        <picker :range="gradeOptions" @change="(e) => form.grade = gradeOptions[e.detail.value]">
          <view class="form-input picker">{{ form.grade || '请选择年级' }}</view>
        </picker>
      </view>
      <view class="form-item">
        <text class="form-label">年龄</text>
        <input class="form-input" type="number" v-model="form.age" placeholder="选填，如 8" />
      </view>
      <view class="form-item">
        <text class="form-label">家长联系方式</text>
        <input class="form-input" type="number" v-model="form.parent_phone" maxlength="11" placeholder="选填" />
      </view>
      <view class="form-item">
        <text class="form-label">{{ isClub ? '上课场馆' : '小区地址' }}</text>
        <input class="form-input" v-model="form.address" :placeholder="isClub ? '如：大学城体育中心' : '如：某小区某栋'" />
      </view>
      <view class="form-item">
        <text class="form-label">状态</text>
        <view class="chips">
          <view v-for="(s, key) in STUDENT_STATUS" :key="key" class="chip"
                :class="{ active: form.status === key }" @tap="form.status = key">{{ s.label }}</view>
        </view>
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
import { STUDENT_STATUS, GRADE_OPTIONS } from '../../utils/constants'
import { required, checkPhone } from '../../utils/validator'
import { useModeStore } from '../../stores/mode'

const modeStore = useModeStore()
const isClub = computed(() => modeStore.mode === 'club')
const id = ref(0)
const saving = ref(false)

// 学员级「课时到期日」已作废：到期日在课时包上（双端互通时该字段被丢弃），
// 学员表单不再提供，form 不含 expire_date（回填对象里的同名键提交后会被服务端忽略）
// class_group(U8/U10/U12) 已删——那是年龄的字段错位，现为数字 age（与双端同源）
const form = reactive({
  name: '', phone: '', grade: '', parent_phone: '',
  address: '', status: 'active', age: '', note: '',
})

const gradeOptions = GRADE_OPTIONS

async function save() {
  if (saving.value) return
  if (!required(form.name, '姓名')) return
  if (!checkPhone(form.phone)) return
  if (!checkPhone(form.parent_phone, '家长手机号')) return
  if (form.age !== '' && form.age !== null && form.age !== undefined) {
    if (!checkNumber(form.age, '年龄', 3)) return
    form.age = Number(form.age)
  } else {
    form.age = null
  }
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
