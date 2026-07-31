<template>
  <div class="wizard-page">
    <div class="wizard-shell glass-card">
      <header class="wizard-header">
        <el-button text circle @click="router.push('/scl/modeling')"
          ><el-icon><ArrowLeft /></el-icon
        ></el-button>
        <div>
          <div class="eyebrow">CREATE FROM SCRATCH</div>
          <h1>{{ $t("modeling.createWizard.title") }}</h1>
          <p>
            {{ $t("modeling.createWizard.description") }}
          </p>
        </div>
      </header>

      <el-steps :active="activeStep" finish-status="success" align-center>
        <el-step
          :title="$t('modeling.createWizard.step1Title')"
          :description="$t('modeling.createWizard.step1Desc')"
        />
        <el-step
          :title="$t('modeling.createWizard.step2Title')"
          :description="$t('modeling.createWizard.step2Desc')"
        />
        <el-step
          :title="$t('modeling.createWizard.step3Title')"
          :description="$t('modeling.createWizard.step3Desc')"
        />
      </el-steps>

      <main class="wizard-body">
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
        >
          <section v-show="activeStep === 0" class="step-panel">
            <div class="section-title">
              <span>01</span>
              <div>
                <h2>{{ $t("modeling.createWizard.section1Title") }}</h2>
                <p>{{ $t("modeling.createWizard.section1Desc") }}</p>
              </div>
            </div>
            <div class="form-grid">
              <el-form-item
                :label="$t('modeling.createWizard.projectName')"
                prop="name"
              >
                <el-input
                  v-model="form.name"
                  maxlength="128"
                  :placeholder="
                    $t('modeling.createWizard.projectNamePlaceholder')
                  "
                />
              </el-form-item>
              <el-form-item
                :label="$t('modeling.createWizard.projectCode')"
                prop="code"
              >
                <el-input
                  v-model="form.code"
                  maxlength="64"
                  :placeholder="
                    $t('modeling.createWizard.projectCodePlaceholder')
                  "
                />
                <div class="field-tip">
                  {{ $t("modeling.createWizard.codeRule") }}
                </div>
              </el-form-item>
              <el-form-item
                :label="$t('modeling.createWizard.fileType')"
                prop="file_type"
              >
                <el-radio-group
                  v-model="form.file_type"
                  class="file-type-group"
                >
                  <el-radio-button value="ICD">ICD</el-radio-button>
                  <el-radio-button value="CID">CID</el-radio-button>
                  <el-radio-button value="SCD">SCD</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item
                :label="$t('modeling.createWizard.standardVersion')"
                prop="standard_version"
              >
                <el-select v-model="form.standard_version" style="width: 100%">
                  <el-option label="IEC 61850 Ed2.1" value="IEC 61850 Ed2.1" />
                  <el-option label="IEC 61850 Ed2" value="IEC 61850 Ed2" />
                  <el-option label="IEC 61850 Ed1" value="IEC 61850 Ed1" />
                </el-select>
              </el-form-item>
              <el-form-item
                :label="$t('modeling.createWizard.projectDescription')"
                class="full-row"
              >
                <el-input
                  v-model="form.description"
                  type="textarea"
                  :rows="3"
                  maxlength="512"
                  show-word-limit
                  :placeholder="
                    $t('modeling.createWizard.projectDescriptionPlaceholder')
                  "
                />
              </el-form-item>
              <el-form-item
                :label="$t('modeling.createWizard.profiles')"
                class="full-row"
              >
                <el-select
                  v-model="form.profiles"
                  multiple
                  style="width: 100%"
                  :placeholder="$t('modeling.createWizard.profilesPlaceholder')"
                >
                  <el-option
                    v-for="profile in profiles"
                    :key="profile.id"
                    :label="`${profile.name} · ${profile.version}`"
                    :value="profile.id"
                  >
                    <span>{{ profile.name }}</span>
                    <span class="profile-description">{{
                      profile.description
                    }}</span>
                  </el-option>
                </el-select>
                <div class="field-tip">
                  {{ $t("modeling.createWizard.profilesTip") }}
                </div>
              </el-form-item>
            </div>
          </section>

          <section v-show="activeStep === 1" class="step-panel">
            <div class="section-title">
              <span>02</span>
              <div>
                <h2>{{ $t("modeling.createWizard.section2Title") }}</h2>
                <p>
                  {{ $t("modeling.createWizard.section2Desc") }}
                </p>
              </div>
            </div>
            <div class="form-grid">
              <el-form-item
                :label="$t('modeling.createWizard.iedName')"
                prop="ied.name"
              >
                <el-input
                  v-model="form.ied.name"
                  :placeholder="$t('modeling.createWizard.iedNamePlaceholder')"
                />
              </el-form-item>
              <el-form-item
                :label="$t('modeling.createWizard.accessPoint')"
                prop="access_point_name"
              >
                <el-input v-model="form.access_point_name" placeholder="AP1" />
              </el-form-item>
              <el-form-item :label="$t('modeling.createWizard.manufacturer')">
                <el-input
                  v-model="form.ied.manufacturer"
                  :placeholder="
                    $t('modeling.createWizard.manufacturerPlaceholder')
                  "
                />
              </el-form-item>
              <el-form-item :label="$t('modeling.createWizard.deviceType')">
                <el-input
                  v-model="form.ied.type"
                  :placeholder="
                    $t('modeling.createWizard.deviceTypePlaceholder')
                  "
                />
              </el-form-item>
            </div>

            <div class="ld-heading">
              <div>
                <h3>{{ $t("modeling.createWizard.logicalDevices") }}</h3>
                <p>{{ $t("modeling.createWizard.logicalDevicesDesc") }}</p>
              </div>
              <el-button type="primary" plain @click="addLogicalDevice"
                ><el-icon><Plus /></el-icon
                >{{ $t("modeling.createWizard.addLogicalDevice") }}</el-button
              >
            </div>
            <div class="ld-list">
              <div
                v-for="(device, index) in form.logical_devices"
                :key="index"
                class="ld-row"
              >
                <div class="ld-index">LD {{ index + 1 }}</div>
                <el-form-item
                  :prop="`logical_devices.${index}.inst`"
                  :rules="ldRules"
                >
                  <el-input
                    v-model="device.inst"
                    :placeholder="$t('modeling.createWizard.ldInstPlaceholder')"
                  />
                </el-form-item>
                <el-input
                  v-model="device.desc"
                  :placeholder="$t('modeling.createWizard.ldDescPlaceholder')"
                />
                <el-button
                  :disabled="form.logical_devices.length === 1"
                  text
                  circle
                  @click="removeLogicalDevice(index)"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
            </div>
          </section>

          <section v-show="activeStep === 2" class="step-panel review-panel">
            <div class="section-title">
              <span>03</span>
              <div>
                <h2>{{ $t("modeling.createWizard.section3Title") }}</h2>
                <p>{{ $t("modeling.createWizard.section3Desc") }}</p>
              </div>
            </div>
            <div class="review-grid">
              <div class="review-summary">
                <dl>
                  <div>
                    <dt>{{ $t("modeling.createWizard.summaryProject") }}</dt>
                    <dd>
                      {{ form.name }} <small>{{ form.code }}</small>
                    </dd>
                  </div>
                  <div>
                    <dt>{{ $t("modeling.createWizard.summaryOutputType") }}</dt>
                    <dd>{{ form.file_type }} · {{ form.standard_version }}</dd>
                  </div>
                  <div>
                    <dt>IED</dt>
                    <dd>
                      {{ form.ied.name }}
                      <small>{{
                        form.ied.manufacturer ||
                        $t("modeling.createWizard.summaryManufacturer")
                      }}</small>
                    </dd>
                  </div>
                  <div>
                    <dt>
                      {{ $t("modeling.createWizard.summaryLogicalDevices") }}
                    </dt>
                    <dd>
                      {{
                        $t("modeling.createWizard.summaryLdCount", {
                          count: form.logical_devices.length,
                        })
                      }}
                    </dd>
                  </div>
                  <div>
                    <dt>{{ $t("modeling.createWizard.summaryProfiles") }}</dt>
                    <dd>
                      {{
                        $t("modeling.createWizard.summaryLdCount", {
                          count: form.profiles.length,
                        })
                      }}
                    </dd>
                  </div>
                </dl>
                <el-alert
                  type="info"
                  :closable="false"
                  show-icon
                  :title="$t('modeling.createWizard.summaryNote')"
                />
              </div>
              <div class="structure-preview">
                <div class="preview-title">
                  <el-icon><Share /></el-icon
                  >{{ $t("modeling.createWizard.summaryTitle") }}
                </div>
                <div class="tree-line root">{{ form.name }}</div>
                <div class="tree-line level-1">Header</div>
                <div class="tree-line level-1">IED · {{ form.ied.name }}</div>
                <div class="tree-line level-2">
                  AccessPoint · {{ form.access_point_name }}
                </div>
                <div class="tree-line level-3">Server</div>
                <template
                  v-for="device in form.logical_devices"
                  :key="device.inst"
                >
                  <div class="tree-line level-4">
                    LDevice ·
                    {{ device.inst || $t("modeling.createWizard.unnamedLd") }}
                  </div>
                  <div class="tree-line level-5">LLN0</div>
                </template>
                <div class="tree-line level-1">DataTypeTemplates</div>
              </div>
            </div>
          </section>
        </el-form>
      </main>

      <footer class="wizard-footer">
        <el-button
          @click="
            activeStep === 0 ? router.push('/scl/modeling') : activeStep--
          "
        >
          {{
            activeStep === 0
              ? $t("common.cancel")
              : $t("modeling.createWizard.prev")
          }}
        </el-button>
        <div class="step-hint">
          {{ $t("modeling.createWizard.steps", { current: activeStep + 1 }) }}
        </div>
        <el-button v-if="activeStep < 2" type="primary" @click="nextStep">{{
          $t("modeling.createWizard.next")
        }}</el-button>
        <el-button
          v-else
          type="primary"
          :loading="creating"
          @click="createProject"
        >
          {{ $t("modeling.createWizard.create") }}
        </el-button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { ArrowLeft, Delete, Plus, Share } from "@element-plus/icons-vue";
import {
  modelingApi,
  type CreateProjectPayload,
  type ModelingProfile,
} from "@/api/modelingApi";

const router = useRouter();
const { t } = useI18n();
const formRef = ref<FormInstance>();
const activeStep = ref(0);
const creating = ref(false);
const profiles = ref<ModelingProfile[]>([]);
const namePattern = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;

const form = reactive<CreateProjectPayload>({
  name: "",
  code: "",
  description: "",
  file_type: "ICD",
  standard_version: "IEC 61850 Ed2.1",
  ied: { name: "", manufacturer: "", type: "", configVersion: "1.0" },
  access_point_name: "AP1",
  logical_devices: [
    { inst: "LD0", desc: t("modeling.createWizard.defaultLd") },
  ],
  profiles: ["generic-ied-ed2"],
});

const identifierValidator = (
  _rule: unknown,
  value: string,
  callback: (error?: Error) => void,
) => {
  if (!namePattern.test(value || ""))
    callback(new Error(t("modeling.createWizard.codeRule")));
  else callback();
};

const rules: FormRules = {
  name: [
    {
      required: true,
      message: t("modeling.createWizard.nameRequired"),
      trigger: "blur",
    },
  ],
  code: [{ required: true, validator: identifierValidator, trigger: "blur" }],
  "ied.name": [
    { required: true, validator: identifierValidator, trigger: "blur" },
  ],
  access_point_name: [
    {
      required: true,
      message: t("modeling.createWizard.accessPointRequired"),
      trigger: "blur",
    },
  ],
};
const ldRules = [
  { required: true, validator: identifierValidator, trigger: "blur" },
];

function addLogicalDevice() {
  form.logical_devices.push({
    inst: `LD${form.logical_devices.length}`,
    desc: "",
  });
}

function removeLogicalDevice(index: number) {
  if (form.logical_devices.length > 1) form.logical_devices.splice(index, 1);
}

async function nextStep() {
  if (activeStep.value === 0) {
    const fields = ["name", "code", "file_type", "standard_version"];
    const valid = await formRef.value
      ?.validateField(fields)
      .then(() => true)
      .catch(() => false);
    if (!valid) return;
  }
  if (activeStep.value === 1) {
    const valid = await formRef.value
      ?.validate()
      .then(() => true)
      .catch(() => false);
    if (!valid) return;
  }
  activeStep.value += 1;
}

async function createProject() {
  const valid = await formRef.value
    ?.validate()
    .then(() => true)
    .catch(() => false);
  if (!valid) return;
  creating.value = true;
  try {
    const result = await modelingApi.createProject(form);
    ElMessage.success(t("modeling.createWizard.createSuccess"));
    await router.replace(`/scl/modeling/${result.project.id}`);
  } finally {
    creating.value = false;
  }
}

onMounted(async () => {
  profiles.value = await modelingApi.listProfiles();
});
</script>

<style scoped lang="scss">
.wizard-page {
  height: 100%;
  min-height: 0;
  flex: 1;
  padding: 20px;
  overflow: auto;
  box-sizing: border-box;
  background: var(--bg-main);
}
.wizard-shell {
  width: min(1040px, 100%);
  min-height: 680px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.wizard-header {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 24px 28px 18px;
  border-bottom: 1px solid var(--sidebar-border);
}
.eyebrow {
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.4px;
}
h1 {
  margin: 4px 0;
  color: var(--text-primary);
  font-size: 24px;
}
.wizard-header p,
.section-title p,
.ld-heading p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}
.el-steps {
  padding: 22px 72px 16px;
  background: color-mix(in srgb, var(--panel-bg) 94%, var(--color-primary));
}
.wizard-body {
  flex: 1;
  padding: 20px 54px;
}
.step-panel {
  animation: fade-in 0.2s ease;
}
@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}
.section-title {
  display: flex;
  gap: 14px;
  align-items: center;
  margin-bottom: 22px;
}
.section-title > span {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 11px;
  color: var(--color-primary);
  background: var(--item-active-bg);
  font-weight: 700;
}
.section-title h2 {
  margin: 0 0 3px;
  color: var(--text-primary);
  font-size: 18px;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px 24px;
}
.full-row {
  grid-column: 1 / -1;
}
.field-tip {
  margin-top: 5px;
  color: var(--text-secondary);
  font-size: 11px;
}
.profile-description {
  float: right;
  max-width: 58%;
  color: var(--text-secondary);
  font-size: 12px;
}
.file-type-group {
  width: 100%;
}
.file-type-group :deep(.el-radio-button) {
  width: 33.333%;
}
.file-type-group :deep(.el-radio-button__inner) {
  width: 100%;
}
.ld-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 16px 0 10px;
}
.ld-heading h3 {
  margin: 0 0 3px;
  font-size: 15px;
}
.ld-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.ld-row {
  display: grid;
  grid-template-columns: 60px 1fr 1.5fr 34px;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid var(--sidebar-border);
  border-radius: 10px;
  background: var(--bg-main);
}
.ld-row .el-form-item {
  margin: 0;
}
.ld-index {
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 700;
}
.review-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 22px;
}
.review-summary,
.structure-preview {
  padding: 18px;
  border: 1px solid var(--sidebar-border);
  border-radius: 12px;
}
dl {
  margin: 0 0 18px;
}
dl > div {
  display: grid;
  grid-template-columns: 90px 1fr;
  padding: 10px 0;
  border-bottom: 1px solid var(--sidebar-border);
}
dt {
  color: var(--text-secondary);
  font-size: 13px;
}
dd {
  margin: 0;
  color: var(--text-primary);
  font-weight: 600;
}
dd small {
  display: block;
  margin-top: 3px;
  color: var(--text-secondary);
  font-weight: 400;
}
.preview-title {
  display: flex;
  gap: 7px;
  align-items: center;
  margin-bottom: 12px;
  font-weight: 600;
}
.tree-line {
  position: relative;
  padding: 5px 8px;
  color: var(--text-secondary);
  font-size: 12px;
}
.tree-line::before {
  content: "└";
  margin-right: 7px;
  color: #94a3b8;
}
.tree-line.root {
  color: var(--text-primary);
  font-weight: 700;
}
.tree-line.root::before {
  content: "◆";
  color: var(--color-primary);
}
.level-1 {
  margin-left: 14px;
}
.level-2 {
  margin-left: 34px;
}
.level-3 {
  margin-left: 54px;
}
.level-4 {
  margin-left: 74px;
}
.level-5 {
  margin-left: 94px;
}
.wizard-footer {
  display: flex;
  align-items: center;
  padding: 16px 28px;
  border-top: 1px solid var(--sidebar-border);
}
.step-hint {
  flex: 1;
  text-align: center;
  color: var(--text-secondary);
  font-size: 12px;
}

@container (max-width: 800px) {
  .wizard-body {
    padding: 20px;
  }
  .el-steps {
    padding-inline: 20px;
  }
  .form-grid,
  .review-grid {
    grid-template-columns: 1fr;
  }
  .ld-row {
    grid-template-columns: 50px 1fr 34px;
  }
  .ld-row > .el-input {
    grid-column: 2 / 3;
  }
}
</style>
