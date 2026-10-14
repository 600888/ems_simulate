<template>
  <main class="preview-page">
    <header>
      <div>
        <h1>DL/T 698.45</h1>
        <span>{{
          l("设备工作区 · 界面预览", "Device workspace · UI preview")
        }}</span>
      </div>
      <div class="header-actions">
        <el-radio-group v-model="role"
          ><el-radio-button value="client">{{
            l("客户端", "Client")
          }}</el-radio-button
          ><el-radio-button value="server">{{
            l("服务端", "Server")
          }}</el-radio-button></el-radio-group
        ><el-button
          @click="setLocale(currentLocale === 'en-US' ? 'zh-CN' : 'en-US')"
          >{{ locale === "en-US" ? "中文" : "EN" }}</el-button
        ><router-link to="/"
          ><el-button>{{
            l("返回应用", "Back to app")
          }}</el-button></router-link
        >
      </div>
    </header>
    <section class="status-row">
      <TextNode
        icon-type="address"
        :label="l('通信端点', 'Endpoint')"
        name="127.0.0.1 : 6980"
      />
      <TextNode
        icon-type="comm"
        :label="l('通信类型', 'Protocol role')"
        :name="role === 'client' ? 'Dlt698Client' : 'Dlt698Server'"
      />
      <TextNode
        icon-type="device-status"
        :label="l('设备状态', 'Device status')"
        :name="l('未连接 · 预览', 'Disconnected · preview')"
        :status="false"
      />
      <div class="status-actions">
        <el-button type="primary" disabled>{{
          l("开启设备", "Start device")
        }}</el-button
        ><el-tooltip
          :content="
            l(
              '真实设备接入后复用公共报文窗口和连接监控',
              'Connected devices use the shared message viewer and connection monitor',
            )
          "
          ><span
            ><el-button disabled>{{
              l("查看报文", "View messages")
            }}</el-button></span
          ></el-tooltip
        >
      </div>
    </section>
    <section class="simulation-row">
      <TextNode
        icon-type="sim-status"
        :label="l('数据模拟', 'Simulation')"
        :name="l('已停止', 'Stopped')"
        :status="false"
      /><el-button disabled>{{
        l("模拟配置", "Simulation settings")
      }}</el-button
      ><el-button type="success" disabled>{{
        l("开始模拟", "Start simulation")
      }}</el-button
      ><small>{{
        role === "client"
          ? l("客户端不支持数据模拟", "Simulation is unavailable for clients")
          : l(
              "真实设备接入后复用公共模拟配置",
              "Connected devices use shared simulation settings",
            )
      }}</small>
    </section>
    <Dlt698Panel
      :key="role"
      :channel-id="0"
      :device-name="`DLT698-PREVIEW-${role}`"
      :role="role"
      :running="false"
      preview
    />
  </main>
</template>
<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { currentLocale, setLocale } from "@/composables/useAppSettings";
import type { Dlt698Role } from "@/types/dlt698";
import { useDlt698Text } from "@/composables/useDlt698Text";
import TextNode from "@/components/common/TextNode.vue";
import Dlt698Panel from "@/components/device/dlt698/Dlt698Panel.vue";
const role = ref<Dlt698Role>("client");
const { locale } = useI18n();
const l = useDlt698Text();
</script>
<style scoped>
.preview-page {
  box-sizing: border-box;
  min-height: 100vh;
  padding: 20px 28px 40px;
  background: var(--bg-main);
  color: var(--text-primary);
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}
header > div:first-child {
  display: flex;
  align-items: baseline;
  gap: 16px;
}
h1 {
  font-size: 23px;
  margin: 0;
}
header span,
small {
  color: var(--text-secondary);
  font-size: 13px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.status-row,
.simulation-row {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--panel-bg);
  padding: 16px;
  margin-bottom: 12px;
}
.status-actions {
  display: flex;
  gap: 12px;
  margin-left: auto;
}
.simulation-row {
  gap: 12px;
}
@media (max-width: 900px) {
  .preview-page {
    padding: 12px;
  }
  header {
    flex-wrap: wrap;
  }
  header > div:first-child {
    flex-wrap: wrap;
    gap: 6px;
  }
  .header-actions {
    flex-wrap: wrap;
  }
}
</style>
