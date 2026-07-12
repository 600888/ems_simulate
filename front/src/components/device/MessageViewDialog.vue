<template>
  <el-dialog
    v-model="visible"
    :title="$t('messageView.title')"
    width="1100px"
    :before-close="handleClose"
    destroy-on-close
    class="message-dialog"
  >
    <MessageViewPanel :device-name="deviceName" :active="visible" />
    <template #footer>
      <el-button @click="handleClose">{{ $t('common.close') }}</el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import MessageViewPanel from './MessageViewPanel.vue'

const props = defineProps<{ modelValue: boolean; deviceName: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

function handleClose() {
  visible.value = false
}
</script>

<style lang="scss" scoped>
.message-dialog :deep(.el-dialog__body) {
  padding: 16px 20px;
}
</style>
