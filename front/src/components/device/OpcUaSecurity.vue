<template>
  <div>
    <OpcUaPageHeading
      :title="t('opcua.security')"
      :description="t('opcua.securityDescription')"
    />
    <el-alert
      :title="t('opcua.securityHint')"
      type="warning"
      :closable="false"
    />
    <section class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.endpointSecurity") }}</h3>
      </div>
      <el-form label-position="top" class="ua-form-grid" :disabled="running">
        <el-form-item :label="t('opcua.securityMode')"
          ><el-select v-model="security.mode"
            ><el-option
              v-for="mode in ['None', 'Sign', 'SignAndEncrypt']"
              :key="mode"
              :label="mode"
              :value="mode" /></el-select
        ></el-form-item>
        <el-form-item label="Application URI" class="ua-span-2"
          ><el-input v-model="security.application_uri"
        /></el-form-item>
        <el-form-item
          v-if="role === 'server'"
          :label="t('opcua.advertisedHost')"
          ><el-input v-model="security.advertised_host"
        /></el-form-item>
        <el-form-item v-if="role === 'client'" :label="t('opcua.identity')"
          ><el-select v-model="security.identity"
            ><el-option
              :label="t('opcua.anonymous')"
              value="anonymous" /><el-option
              :label="t('opcua.username')"
              value="username" /></el-select
        ></el-form-item>
        <template v-if="role === 'client' && security.identity === 'username'">
          <el-form-item :label="t('opcua.username')"
            ><el-input v-model="security.username"
          /></el-form-item>
          <el-form-item :label="t('opcua.password')"
            ><el-input
              v-model="password"
              type="password"
              show-password
              autocomplete="new-password"
          /></el-form-item>
        </template>
        <el-form-item v-if="role === 'server'" :label="t('opcua.anonymous')"
          ><el-switch v-model="security.allow_anonymous"
        /></el-form-item>
      </el-form>
      <div class="ua-form-footer">
        <el-button
          :disabled="running"
          :loading="busy"
          type="primary"
          @click="save"
          >{{ t("opcua.saveConfig") }}</el-button
        >
      </div>
    </section>
    <section class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.applicationCertificate") }}</h3>
        <el-tag
          :type="security.certificate ? 'success' : 'info'"
          effect="light"
          >{{
            t(
              security.certificate
                ? "opcua.certificateReady"
                : "opcua.noCertificate",
            )
          }}</el-tag
        >
      </div>
      <el-form label-position="top" class="ua-form-grid">
        <el-form-item label="Application URI" class="ua-span-2"
          ><span class="ua-code">{{
            security.application_uri || "—"
          }}</span></el-form-item
        >
        <el-form-item :label="t('opcua.certificateHost')"
          ><el-input v-model="certificateHost" :disabled="running"
        /></el-form-item>
      </el-form>
      <el-button :disabled="running" :loading="busy" @click="generate">{{
        t("opcua.generateCertificate")
      }}</el-button>
    </section>
    <section class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.endpointDiscovery") }}</h3>
      </div>
      <div class="ua-toolbar">
        <el-input
          v-model="endpoint"
          placeholder="opc.tcp://127.0.0.1:4840/ems/"
        /><el-button :loading="busy" @click="discover">{{
          t("opcua.discoverEndpoints")
        }}</el-button>
      </div>
      <el-table :data="endpoints" stripe>
        <el-table-column
          prop="endpoint_url"
          label="Endpoint"
          min-width="260"
          show-overflow-tooltip
        />
        <el-table-column
          prop="security_mode"
          :label="t('opcua.securityMode')"
          width="170"
        />
        <el-table-column
          prop="application_uri"
          label="Application URI"
          min-width="240"
          show-overflow-tooltip
        />
      </el-table>
    </section>
    <section class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.trustList") }}</h3>
        <span>{{ peers.length }} {{ t("opcua.certificate") }}</span>
      </div>
      <el-table :data="peers" stripe>
        <el-table-column
          prop="subject"
          :label="t('opcua.certificate')"
          min-width="200"
          show-overflow-tooltip
        />
        <el-table-column
          prop="fingerprint"
          :label="t('opcua.fingerprint')"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column :label="t('opcua.trust')" width="110"
          ><template #default="{ row }"
            ><el-tag
              size="small"
              :type="
                security.trusted.includes(row.fingerprint)
                  ? 'success'
                  : 'warning'
              "
              >{{
                t(
                  security.trusted.includes(row.fingerprint)
                    ? "opcua.trusted"
                    : "opcua.pendingTrust",
                )
              }}</el-tag
            ></template
          ></el-table-column
        >
        <el-table-column
          prop="valid_until"
          :label="t('opcua.validUntil')"
          min-width="200"
        />
        <el-table-column :label="t('opcua.actions')" width="130"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              :disabled="busy"
              @click="trust(row)"
              >{{
                t(
                  security.trusted.includes(row.fingerprint)
                    ? "opcua.revokeTrust"
                    : "opcua.approveTrust",
                )
              }}</el-button
            ></template
          ></el-table-column
        >
      </el-table>
    </section>
    <p class="ua-note">{{ t("opcua.liveAccessHint") }}</p>
    <section v-if="role === 'server'" class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.userIdentity") }}</h3>
      </div>
      <el-form label-position="top" class="ua-form-grid" :disabled="busy">
        <el-form-item :label="t('opcua.username')"
          ><el-input v-model="username"
        /></el-form-item>
        <el-form-item :label="t('opcua.role')"
          ><el-select v-model="userRole"
            ><el-option :label="t('opcua.viewer')" value="viewer" /><el-option
              :label="t('opcua.operator')"
              value="operator" /></el-select
        ></el-form-item>
        <el-form-item :label="t('opcua.password')"
          ><el-input
            v-model="userPassword"
            type="password"
            show-password
            autocomplete="new-password"
        /></el-form-item>
      </el-form>
      <div class="ua-form-footer">
        <el-button :disabled="busy" :loading="busy" @click="userSave">{{
          t("opcua.saveUser")
        }}</el-button>
      </div>
      <el-table :data="security.users" stripe class="users-table">
        <el-table-column prop="username" :label="t('opcua.username')" />
        <el-table-column :label="t('opcua.role')"
          ><template #default="{ row }">{{
            row.role ? t("opcua." + row.role) : "—"
          }}</template></el-table-column
        >
        <el-table-column :label="t('opcua.actions')" width="120"
          ><template #default="{ row }"
            ><el-button
              :disabled="busy"
              link
              type="danger"
              @click="removeUser(row)"
              >{{ t("opcua.delete") }}</el-button
            ></template
          ></el-table-column
        >
      </el-table>
    </section>
  </div>
</template>
<script setup lang="ts">
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import { onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getOpcUaConfig,
  getOpcUaFeatures,
  saveOpcUaFeature,
  generateOpcUaCertificate,
  discoverOpcUaEndpoints,
  trustOpcUaCertificate,
  saveOpcUaPassword,
  saveOpcUaUser,
} from "@/api/opcuaApi";
import { showError } from "@/api/http";
const props = defineProps<{
  channelId: number;
  role: "client" | "server";
  running: boolean;
}>();
const { t } = useI18n();
const security = ref<any>({
  mode: "None",
  application_uri: "",
  identity: "anonymous",
  username: "",
  allow_anonymous: false,
  trusted: [],
  users: [],
});
const busy = ref(false),
  password = ref(""),
  endpoint = ref(""),
  certificateHost = ref("127.0.0.1");
const peers = ref<any[]>([]),
  endpoints = ref<any[]>([]),
  username = ref(""),
  userPassword = ref(""),
  userRole = ref("viewer");
async function load() {
  try {
    const features = await getOpcUaFeatures(props.channelId);
    security.value = {
      mode: "None",
      application_uri: `urn:ems-simulate:channel:${props.channelId}`,
      identity: "anonymous",
      username: "",
      allow_anonymous: false,
      trusted: [],
      users: [],
      ...features.security,
    };
    peers.value = features.certificates?.peers || [];
    endpoint.value = (await getOpcUaConfig(props.channelId)).endpoint_url;
  } catch (e) {
    showError(e);
  }
}
async function action(task: () => Promise<unknown>) {
  busy.value = true;
  try {
    await task();
    await load();
    ElMessage.success(t("opcua.configSaved"));
  } catch (e) {
    if (e !== "cancel" && e !== "close") showError(e);
  } finally {
    busy.value = false;
  }
}
async function save() {
  await action(async () => {
    if (password.value) {
      await saveOpcUaPassword(props.channelId, password.value);
      password.value = "";
    }
    await saveOpcUaFeature(props.channelId, "security", security.value);
  });
}
async function generate() {
  await action(async () => {
    await ElMessageBox.confirm(
      t("opcua.generateConfirm"),
      t("opcua.generateCertificate"),
    );
    return generateOpcUaCertificate(
      props.channelId,
      security.value.application_uri,
      certificateHost.value,
    );
  });
}
async function discover() {
  await action(async () => {
    endpoints.value = (
      await discoverOpcUaEndpoints(props.channelId, endpoint.value)
    ).endpoints;
  });
}
async function trust(peer: any) {
  await action(async () => {
    await ElMessageBox.confirm(
      `${peer.subject}\nSHA-256: ${peer.fingerprint}`,
      t("opcua.trust"),
    );
    return trustOpcUaCertificate(
      props.channelId,
      peer.fingerprint,
      !security.value.trusted.includes(peer.fingerprint),
    );
  });
}
async function userSave() {
  await action(async () => {
    await saveOpcUaUser(
      props.channelId,
      username.value,
      userRole.value,
      userPassword.value,
    );
    userPassword.value = "";
  });
}
async function removeUser(user: any) {
  await action(async () => {
    await ElMessageBox.confirm(t("opcua.deleteUserConfirm"), t("opcua.delete"));
    return saveOpcUaUser(props.channelId, user.username, user.role, null);
  });
}
onMounted(load);
watch(() => props.channelId, load);
</script>
<style scoped>
.users-table {
  margin-top: 16px;
}
</style>
