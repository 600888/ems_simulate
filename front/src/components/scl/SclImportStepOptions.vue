<template>
  <div class="import-step-options">
    <el-form label-position="top">
      <el-form-item :label="$t('scl.selectChannel')">
        <el-select v-model="channelId" :placeholder="$t('scl.channelPlaceholder')" style="width: 100%">
          <el-option
            v-for="ch in channelList"
            :key="ch.id"
            :label="ch.name || `通道 ${ch.id}`"
            :value="ch.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-checkbox v-model="overwrite">
          {{ $t('scl.overwriteData') }}
        </el-checkbox>
        <div class="form-hint">{{ $t('scl.overwriteHint') }}</div>
      </el-form-item>

      <el-form-item>
        <el-checkbox v-model="importGoose">
          {{ $t('scl.importGoose') }}
        </el-checkbox>
        <div v-if="importGoose" class="sub-option">
          <el-input
            v-model="gooseInterface"
            :placeholder="$t('scl.interfacePlaceholder')"
            style="width: 240px"
          />
        </div>
      </el-form-item>

      <el-form-item>
        <el-checkbox v-model="importReports">
          {{ $t('scl.importReports') }}
        </el-checkbox>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getChannelList } from '@/api/channelApi'
import type { ChannelInfo } from '@/types/channel'

const channelList = ref<ChannelInfo[]>([])
const channelId = ref<number>(0)
const overwrite = ref(false)
const importGoose = ref(true)
const gooseInterface = ref('eth0')
const importReports = ref(false)

onMounted(async () => {
  try {
    channelList.value = await getChannelList()
  } catch {
    channelList.value = []
  }
})

defineExpose({ channelId, overwrite, importGoose, gooseInterface, importReports })
</script>

<style scoped>
.form-hint { font-size: 11px; color: #999; margin-top: 4px; }
.sub-option { margin-top: 8px; }
</style>
