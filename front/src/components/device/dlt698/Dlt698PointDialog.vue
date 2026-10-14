<template>
  <component
    :is="inline ? 'section' : ElDialog"
    :class="inline ? 'inline-editor' : 'dlt698-point-dialog'"
    :model-value="visible"
    @update:model-value="visible = $event"
    :title="point ? l('编辑测点', 'Edit point') : l('添加测点', 'Add point')"
    width="800px"
    top="6vh"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <el-form
      class="point-editor-form"
      label-position="top"
      :disabled="busy"
      @submit.prevent="save"
    >
      <section class="form-section">
        <div class="section-heading">
          <div>
            <h4>{{ l("基本信息", "Basic information") }}</h4>
            <p>
              {{
                l(
                  "设置测点的名称、分类与写入权限",
                  "Name, category and write permissions",
                )
              }}
            </p>
          </div>
          <el-tag
            :type="draft.standard ? 'primary' : 'info'"
            effect="plain"
            size="small"
            >{{
              draft.standard
                ? l("标准测点", "Standard point")
                : l("自定义测点", "Custom point")
            }}</el-tag
          >
        </div>
        <div class="field-grid">
          <el-form-item :label="l('测点编码', 'Point code')"
            ><el-input v-model="draft.code"
          /></el-form-item>
          <el-form-item :label="l('测点名称', 'Point name')"
            ><el-input v-model="draft.name"
          /></el-form-item>
          <el-form-item :label="l('分类', 'Category')">
            <el-select v-model="draft.category">
              <el-option
                v-for="category in categories"
                :key="category.value"
                :label="l(category.zh, category.en)"
                :value="category.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="l('远端 SET 权限', 'Remote SET permission')">
            <div class="permission-field">
              <div class="switch-line">
                <el-switch
                  v-model="draft.writable"
                  :disabled="draft.standard || role === 'server'"
                /><span>{{
                  draft.writable
                    ? l("允许远端写入", "Remote writes enabled")
                    : l("只读", "Read only")
                }}</span>
              </div>
              <p class="field-hint">
                {{
                  l(
                    role === "server"
                      ? "当前服务端发布只读属性"
                      : "实际写入权限由对端决定",
                    role === "server"
                      ? "The server publishes read-only attributes"
                      : "The peer controls write permission",
                  )
                }}
              </p>
            </div>
          </el-form-item>
        </div>
      </section>

      <section class="form-section">
        <div class="section-heading">
          <div>
            <h4>{{ l("对象地址", "Object address") }}</h4>
            <p>
              {{
                l(
                  "由 OI、属性字节与元素索引组成 OAD",
                  "OAD combines the OI, attribute byte and element index",
                )
              }}
            </p>
          </div>
        </div>
        <div class="field-grid address-grid">
          <el-form-item label="OI"
            ><el-input v-model="oi" maxlength="4" :disabled="draft.standard" />
            <p class="field-hint">
              {{
                l(
                  "4 位十六进制对象标识",
                  "4-digit hexadecimal object identifier",
                )
              }}
            </p></el-form-item
          >
          <el-form-item :label="l('属性字节', 'Attribute byte')"
            ><el-input-number
              v-model="attribute"
              :min="0"
              :max="255"
              controls-position="right"
              :disabled="draft.standard"
            />
            <p class="field-hint">
              {{ l("十进制，范围 0–255", "Decimal, from 0 to 255") }}
            </p></el-form-item
          >
          <el-form-item :label="l('元素索引', 'Element index')"
            ><el-input-number
              v-model="index"
              :min="0"
              :max="255"
              controls-position="right"
              :disabled="draft.standard"
            />
            <p class="field-hint">
              {{
                l(
                  "0 = 完整属性；1 起为元素",
                  "0 = whole attribute; elements start at 1",
                )
              }}
            </p></el-form-item
          >
        </div>
        <div class="oad-preview">
          <span>{{ l("OAD 地址", "OAD address") }}</span
          ><code>{{ oad || "—" }}</code
          ><span v-if="draft.standard" class="oad-note">{{
            l("标准地址不可修改", "Standard address is locked")
          }}</span>
        </div>
      </section>

      <section class="form-section">
        <div class="section-heading">
          <div>
            <h4>{{ l("数值与初始值", "Scaling and initial value") }}</h4>
            <p>
              {{
                draft.standard
                  ? l(
                      "标准单位、倍率和 Data 类型由点表定义",
                      "Standard units, scaler and Data type follow the catalog",
                    )
                  : l(
                      "配置显示换算与测点的初始 Data",
                      "Configure display scaling and the initial Data value",
                    )
              }}
            </p>
          </div>
        </div>
        <div class="field-grid">
          <el-form-item :label="l('单位', 'Unit')"
            ><el-input
              v-model="draft.unit"
              :disabled="draft.standard"
              :placeholder="l('例如 V、A、kWh', 'e.g. V, A, kWh')"
          /></el-form-item>
          <el-form-item :label="l('倍率指数', 'Scaler exponent')"
            ><el-input-number
              v-model="draft.scaler"
              :min="-12"
              :max="12"
              controls-position="right"
              :disabled="draft.standard"
            />
            <p class="field-hint">
              {{ l("工程值 = 原始值 ×", "Engineering value = raw value ×") }}
              10<sup>{{ draft.scaler }}</sup>
            </p></el-form-item
          >
        </div>
        <div class="initial-value-field">
          <Dlt698DataEditor
            v-model="draft.initial_value"
            :locked="draft.standard"
            structured
            @valid="dataValid = $event"
          />
        </div>
      </section>
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
        show-icon
      />
    </el-form>
    <div v-if="inline" class="editor-actions">
      <el-button
        type="primary"
        :disabled="!dataValid || !oad || busy"
        :loading="busy"
        @click="save"
        >{{ l("保存修改", "Save changes") }}</el-button
      >
    </div>
    <template v-if="!inline" #footer
      ><div class="dialog-actions">
        <el-button @click="visible = false">{{ l("取消", "Cancel") }}</el-button
        ><el-button
          type="primary"
          :disabled="!dataValid || !oad || busy"
          :loading="busy"
          @click="save"
          >{{ l("保存", "Save") }}</el-button
        >
      </div></template
    >
  </component>
</template>
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElDialog } from "element-plus";
import type { Dlt698Point } from "@/types/dlt698";
import { makeOad, validateData } from "@/utils/dlt698";
import Dlt698DataEditor from "./Dlt698DataEditor.vue";
import { useDlt698Text } from "@/composables/useDlt698Text";
const props = defineProps<{
  modelValue: boolean;
  inline?: boolean;
  point?: Dlt698Point;
  busy?: boolean;
  saveError?: string;
  role?: "client" | "server";
}>();
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "save", point: Dlt698Point): void;
}>();
const l = useDlt698Text();
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});
const blank = (): Dlt698Point => ({
  code: "",
  name: "",
  oad: "F0010200",
  category: "parameter",
  data_type: "UInt16",
  unit: "",
  scaler: 0,
  standard: false,
  writable: false,
  initial_value: { type: "UInt16", value: "0" },
});
const draft = ref(blank()),
  oi = ref("F001"),
  attribute = ref(2),
  index = ref(0),
  dataValid = ref(true),
  localError = ref("");
const error = computed(() => props.saveError || localError.value);
const categories = [
  { value: "energy", zh: "电能量", en: "Energy" },
  { value: "demand", zh: "最大需量", en: "Demand" },
  { value: "variable", zh: "变量", en: "Variables" },
  { value: "harmonic", zh: "谐波", en: "Harmonics" },
  { value: "parameter", zh: "参数", en: "Parameters" },
];
const oad = computed(() => {
  try {
    return makeOad(oi.value, attribute.value, index.value);
  } catch {
    return "";
  }
});
watch(
  () => [props.modelValue, props.point?.code],
  ([opened]) => {
    if (opened) {
      draft.value = JSON.parse(JSON.stringify(props.point || blank()));
      oi.value = draft.value.oad.slice(0, 4);
      attribute.value = parseInt(draft.value.oad.slice(4, 6), 16);
      index.value = parseInt(draft.value.oad.slice(6), 16);
      localError.value = "";
    }
  },
  { immediate: true },
);
function save() {
  if (props.busy || !dataValid.value || !oad.value) return;
  try {
    validateData(draft.value.initial_value);
  } catch (e) {
    localError.value = (e as Error).message;
    return;
  }
  if (!draft.value.code.trim() || !draft.value.name.trim()) {
    localError.value = l(
      "请填写测点编码和名称",
      "Point code and name are required",
    );
    return;
  }
  emit("save", {
    ...draft.value,
    code: draft.value.code.trim(),
    name: draft.value.name.trim(),
    oad: oad.value,
    data_type: draft.value.initial_value.type,
  });
}
</script>
<style scoped>
.inline-editor {
  width: 100%;
  min-width: 0;
}
.inline-editor .point-editor-form {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.inline-editor .form-section:last-of-type,
.inline-editor .point-editor-form > .el-alert {
  grid-column: 1 / -1;
}
.point-editor-form {
  display: grid;
  gap: 18px;
  min-width: 0;
  container-type: inline-size;
}
.form-section {
  min-width: 0;
  padding: 22px 24px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--panel-bg);
}
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 22px;
}
h4 {
  margin: 0;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
}
.section-heading p {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 20px;
}
.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
  gap: 20px 28px;
}
.address-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.point-editor-form :deep(.el-form-item) {
  min-width: 0;
  margin: 0;
}
.point-editor-form :deep(.el-form-item__label) {
  float: none;
  height: auto;
  margin: 0 0 8px;
  padding: 0;
  line-height: 20px;
  color: var(--text-primary);
}
.point-editor-form :deep(.el-form-item__content) {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  min-width: 0;
  line-height: normal;
}
.point-editor-form :deep(.el-input),
.point-editor-form :deep(.el-select),
.point-editor-form :deep(.el-input-number) {
  width: 100%;
  min-width: 0;
}
.field-hint {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 19px;
  overflow-wrap: anywhere;
}
.switch-line {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 32px;
  font-size: 13px;
}
.oad-preview {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding: 12px 16px;
  margin-top: 20px;
  border-radius: 6px;
  background: var(--bg-subtle);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 20px;
}
.oad-preview code {
  color: var(--el-color-primary);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 1px;
}
.oad-note {
  margin-left: auto;
}
.initial-value-field {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}
.editor-actions {
  display: flex;
  justify-content: flex-end;
  padding: 18px 0 0;
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
.dialog-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
@container (max-width: 1100px) {
  .form-section {
    grid-column: 1 / -1;
  }
}
@container (max-width: 560px) {
  .field-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 20px;
  }
  .form-section {
    padding: 18px;
  }
  .oad-note {
    margin-left: 0;
  }
}
:global(.dlt698-point-dialog) {
  max-width: calc(100vw - 32px);
  padding: 0;
  border-radius: 12px;
}
:global(.dlt698-point-dialog .el-dialog__header) {
  padding: 20px 24px;
  margin: 0;
  border-bottom: 1px solid var(--border-color);
}
:global(.dlt698-point-dialog .el-dialog__body) {
  padding: 22px 24px;
  max-height: calc(88vh - 150px);
  overflow-y: auto;
}
:global(.dlt698-point-dialog .el-dialog__footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
}
@media (max-width: 600px) {
  :global(.dlt698-point-dialog .el-dialog__body) {
    padding: 16px;
  }
}
</style>
