<template>
  <el-dialog
    v-model="dialogVisible"
    :title="$t('scl.discoverProgress')"
    width="480px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div class="discovery-content">
      <div class="info-row">
        <span>{{ $t("scl.deviceLabel") }}: {{ deviceName }}</span>
      </div>

      <el-progress
        :percentage="progressPercent"
        :stroke-width="20"
        :text-inside="true"
        striped
        striped-flow
        :status="done ? 'success' : ''"
        class="progress-bar"
      />

      <div class="phase-text">{{ currentMessage }}</div>

      <div class="progress-detail">
        {{
          $t("scl.progressFormat", {
            ld: discoveredLds,
            ldTotal: total,
            ln: discoveredLns,
            lnTotal: total,
          })
        }}
      </div>

      <div class="node-list" v-if="discoveredNodes.length">
        <h5>{{ $t("scl.discoveredNodes") }}</h5>
        <div v-for="(node, i) in discoveredNodes" :key="i" class="node-item">
          ✓ {{ node }}
        </div>
        <div v-if="discoveredNodes.length > 8" class="node-more">...</div>
      </div>
    </div>

    <template #footer>
      <el-button v-if="!done" @click="handleCancel">{{
        $t("scl.cancelDiscovery")
      }}</el-button>
      <el-button v-else type="primary" @click="handleClose">{{
        $t("common.close")
      }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    deviceName: string;
    host?: string;
    port?: number;
    autoStart?: boolean;
  }>(),
  {
    host: "",
    port: 102,
    autoStart: true,
  },
);

const emit = defineEmits<{
  (e: "close"): void;
  (e: "cancel"): void;
}>();

const dialogVisible = ref(true);
const progressPercent = ref(0);
const currentMessage = ref(t("scl.discoveryPreparing"));
const discoveredLds = ref(0);
const discoveredLns = ref(0);
const total = ref(50);
const discoveredNodes = ref<string[]>([]);
const done = ref(false);

let timer: number | null = null;

// Simulated discovery progress for demo
function startSimulation() {
  const phases = [
    {
      at: 10,
      msg: t("scl.discoveryLD", { ld: "LD0" }),
      node: "LD0/LLN0 (DoCB:2 DS:3 RCB:1)",
    },
    {
      at: 25,
      msg: t("scl.discoveryLD", { ld: "LD0" }),
      node: "LD0/MMXU1 (DO:12 DA:48)",
    },
    {
      at: 40,
      msg: t("scl.discoveryLD", { ld: "LD0" }),
      node: "LD0/MMTR1 (DO:8 DA:24)",
    },
    {
      at: 55,
      msg: t("scl.discoveryLD", { ld: "LD0" }),
      node: "LD0/XCBR1 (DO:6 DA:18)",
    },
    {
      at: 70,
      msg: t("scl.discoveryLD", { ld: "LD1" }),
      node: "LD1/LLN0 (DoCB:1 DS:2 RCB:1)",
    },
    {
      at: 85,
      msg: t("scl.discoveryBuilding"),
      node: "LD1/MMXU2 (DO:12 DA:48)",
    },
  ];
  let idx = 0;
  timer = window.setInterval(() => {
    progressPercent.value += 5;
    discoveredLds.value = Math.min(
      Math.floor(progressPercent.value / 20) + 1,
      3,
    );
    discoveredLns.value = Math.min(Math.floor(progressPercent.value / 5), 42);
    if (idx < phases.length && progressPercent.value >= phases[idx].at) {
      currentMessage.value = phases[idx].msg;
      discoveredNodes.value.push(phases[idx].node);
      idx++;
    }
    if (progressPercent.value >= 100) {
      currentMessage.value = t("scl.discoveryDone");
      done.value = true;
      if (timer) clearInterval(timer);
    }
  }, 400);
}

onMounted(() => {
  if (props.autoStart) startSimulation();
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});

function handleCancel() {
  if (timer) clearInterval(timer);
  emit("cancel");
  handleClose();
}

function handleClose() {
  emit("close");
}
</script>

<style scoped>
.discovery-content {
  padding: 8px 0;
}
.info-row {
  margin-bottom: 16px;
  font-size: 13px;
}
.progress-bar {
  margin-bottom: 12px;
}
.phase-text {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.progress-detail {
  font-size: 12px;
  color: #999;
  margin-bottom: 16px;
}
.node-list h5 {
  margin: 0 0 8px 0;
  font-size: 13px;
}
.node-item {
  font-size: 12px;
  color: #52c41a;
  line-height: 1.8;
}
.node-more {
  font-size: 12px;
  color: #999;
}
</style>
