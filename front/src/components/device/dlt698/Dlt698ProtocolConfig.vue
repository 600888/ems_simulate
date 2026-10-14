<template>
  <el-form label-width="180px" :disabled="disabled">
    <el-form-item :label="l('协议角色', 'Protocol role')"
      ><el-radio-group v-model="modelValue.role"
        ><el-radio value="client">{{
          l("客户端 / 主站", "Client / master")
        }}</el-radio
        ><el-radio value="server">{{
          l("服务端 / 电表", "Server / meter")
        }}</el-radio></el-radio-group
      ></el-form-item
    >
    <el-form-item :label="l('服务器地址 SA', 'Server address SA')"
      ><el-input v-model="modelValue.server_address" placeholder="000000000000"
    /></el-form-item>
    <el-form-item :label="l('逻辑地址', 'Logical address')"
      ><el-input-number v-model="modelValue.logical_address" :min="0" :max="3"
    /></el-form-item>
    <el-form-item :label="l('客户端地址 CA', 'Client address CA')"
      ><el-input-number v-model="modelValue.client_address" :min="0" :max="255"
    /></el-form-item>
    <el-form-item :label="l('关联方式', 'Association')"
      ><el-select v-model="modelValue.association"
        ><el-option
          :label="l('公共连接', 'Public connection')"
          value="public" /><el-option
          :label="l('预设关联', 'Preestablished association')"
          value="preestablished" /></el-select
    ></el-form-item>
    <el-form-item
      v-for="field in fields"
      :key="field.key"
      :label="l(field.zh, field.en)"
      ><el-input-number
        v-model="modelValue[field.key]"
        :min="field.min"
        :max="field.max"
    /></el-form-item>
    <el-collapse>
      <el-collapse-item
        :title="
          l('CONNECT 协商与设备布局', 'CONNECT negotiation and device layout')
        "
        name="advanced"
      >
        <el-form-item
          v-for="field in advanced"
          :key="field.key"
          :label="l(field.zh, field.en)"
          ><el-input-number
            v-model="modelValue[field.key]"
            :min="field.min"
            :max="field.max"
          /><el-tag v-if="negotiated?.[field.key] != null" type="success"
            >{{ l("协商", "Negotiated") }}: {{ negotiated[field.key] }}</el-tag
          ></el-form-item
        >
        <el-form-item :label="l('接线方式', 'Wiring')"
          ><el-select v-model="modelValue.wiring"
            ><el-option
              value="three_phase_four_wire"
              :label="l('三相四线', 'Three phase, four wire')" /><el-option
              value="three_phase_three_wire"
              :label="l('三相三线', 'Three phase, three wire')" /><el-option
              value="single_phase"
              :label="l('单相', 'Single phase')" /></el-select
        ></el-form-item>
        <el-form-item :label="l('费率数量', 'Tariff count')"
          ><el-input-number
            v-model="modelValue.tariff_count"
            :min="0"
            :max="255"
        /></el-form-item>
        <el-form-item :label="l('最大谐波次数', 'Maximum harmonic order')"
          ><el-input-number
            v-model="modelValue.harmonic_order"
            :min="1"
            :max="255"
        /></el-form-item>
        <el-alert
          :title="
            l(
              '帧上限不含起止字节；APDU 上限不含链路封装。TCP 方向和协议角色独立配置。',
              'Frame limits exclude start/end bytes; APDU limits exclude link framing. TCP direction and protocol role are independent.',
            )
          "
          type="info"
          :closable="false"
        />
      </el-collapse-item>
    </el-collapse>
    <el-divider>{{ l("安全认证", "Authentication") }}</el-divider>
    <el-alert
      :title="
        securityBackend
          ? l(
              '已配置认证后端；可用机制以运行时能力为准',
              'Authentication backend configured; mechanisms depend on runtime capabilities',
            )
          : l(
              '未配置认证后端；密码、对称认证、签名与 ESAM 暂不可用',
              'Authentication backend missing; password, symmetric, signature and ESAM mechanisms are unavailable',
            )
      "
      :type="securityBackend ? 'info' : 'warning'"
      :closable="false"
      show-icon
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
  </el-form>
</template>
<script setup lang="ts">
import { computed } from "vue";
import type { Dlt698Config } from "@/types/dlt698";
import { configError } from "@/utils/dlt698";
import { useDlt698Text } from "@/composables/useDlt698Text";
const props = defineProps<{
  modelValue: Dlt698Config;
  disabled?: boolean;
  negotiated?: Partial<Dlt698Config>;
  securityBackend?: boolean;
}>();
const l = useDlt698Text();
const error = computed(() => configError(props.modelValue));
const fields = [
  {
    key: "request_timeout_ms",
    zh: "请求超时 (ms)",
    en: "Request timeout (ms)",
    min: 100,
    max: 60000,
  },
  {
    key: "heartbeat_interval_s",
    zh: "LINK / 心跳 (s)",
    en: "LINK / heartbeat (s)",
    min: 0,
    max: 3600,
  },
] as const;
const advanced = [
  {
    key: "protocol_version",
    zh: "协议版本",
    en: "Protocol version",
    min: 0,
    max: 65535,
  },
  {
    key: "send_frame_max",
    zh: "发送帧上限",
    en: "Send frame limit",
    min: 64,
    max: 16383,
  },
  {
    key: "receive_frame_max",
    zh: "接收帧上限",
    en: "Receive frame limit",
    min: 64,
    max: 16383,
  },
  {
    key: "receive_window",
    zh: "接收窗口",
    en: "Receive window",
    min: 1,
    max: 255,
  },
  { key: "apdu_max", zh: "APDU 上限", en: "APDU limit", min: 64, max: 65535 },
  {
    key: "association_timeout_s",
    zh: "关联超时 (s)",
    en: "Association timeout (s)",
    min: 1,
    max: 86400,
  },
] as const;
</script>
