<template>
  <el-drawer
    v-model="visible"
    :title="$t('device.messageDetailTitle')"
    size="min(760px, 100vw)"
    resizable
    append-to-body
    destroy-on-close
    class="message-detail-drawer"
  >
    <template #header="{ titleId, titleClass }">
      <div class="drawer-title-content">
        <span :id="titleId" :class="titleClass">{{
          $t("device.messageDetailTitle")
        }}</span>
        <el-tooltip
          :content="$t('device.messageDragHintTooltip')"
          placement="bottom"
        >
          <span class="resize-hint">
            <el-icon><Rank /></el-icon>
            <span>{{ $t("device.dragToResize") }}</span>
          </span>
        </el-tooltip>
      </div>
    </template>
    <div v-loading="loading" class="detail-body">
      <template v-if="detail">
        <el-alert
          :title="detail.summary"
          :type="detail.valid ? 'success' : 'error'"
          :closable="false"
          show-icon
        />

        <el-descriptions :column="3" border class="section">
          <el-descriptions-item :label="$t('device.messageProtocol')">{{
            detail.protocol
          }}</el-descriptions-item>
          <el-descriptions-item :label="$t('device.messageFrameType')">{{
            detail.frame_kind
          }}</el-descriptions-item>
          <el-descriptions-item :label="$t('device.messageDirection')"
            >{{ detail.direction }} /
            {{ detail.msg_type }}</el-descriptions-item
          >
          <el-descriptions-item :label="$t('device.messageTime')">{{
            detail.formatted_time
          }}</el-descriptions-item>
          <el-descriptions-item :label="$t('device.messageLength')"
            >{{ detail.raw_length }}
            {{ $t("device.messageLengthUnit") }}</el-descriptions-item
          >
          <el-descriptions-item :label="$t('device.messageParseStatus')">
            <el-tag
              :type="
                detail.valid
                  ? detail.complete
                    ? 'success'
                    : 'warning'
                  : 'danger'
              "
              size="small"
            >
              {{
                detail.valid
                  ? detail.complete
                    ? $t("device.messageComplete")
                    : $t("device.messagePartial")
                  : $t("device.messageVerifyFailed")
              }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <section class="section">
          <h3>{{ $t("device.messageRawMessage") }}</h3>
          <div class="raw-frame">
            <span
              v-for="(byte, index) in rawBytes"
              :key="index"
              class="raw-byte"
              :class="{ selected: isSelectedByte(index) }"
              :title="$t('device.messageByte', { index })"
              >{{ byte }}</span
            >
          </div>
          <div class="raw-hint">{{ $t("device.messageClickToHighlight") }}</div>
        </section>

        <section class="section">
          <h3>{{ $t("device.messageFieldParse") }}</h3>
          <el-table
            :data="detail.fields"
            border
            size="small"
            max-height="360"
            highlight-current-row
            :header-cell-style="{ whiteSpace: 'nowrap' }"
            @row-click="selectField"
          >
            <el-table-column :label="$t('device.messageBytesCol')" width="82">
              <template #default="{ row }">{{
                byteRange(row.offset, row.length)
              }}</template>
            </el-table-column>
            <el-table-column
              prop="raw_hex"
              :label="$t('device.messageRawHex')"
              min-width="110"
            />
            <el-table-column
              prop="name"
              :label="$t('device.messageField')"
              width="130"
            />
            <el-table-column
              prop="display_value"
              :label="$t('device.messageParsedValue')"
              min-width="150"
            />
            <el-table-column
              prop="description"
              :label="$t('device.messageDescription')"
              min-width="150"
            />
          </el-table>
        </section>

        <section v-if="displayObjects.length" class="section">
          <h3>{{ $t("device.messageDataObjects") }}</h3>
          <el-table
            :data="displayObjects"
            border
            size="small"
            max-height="280"
            highlight-current-row
            @row-click="handleObjectRowClick"
          >
            <el-table-column type="expand" width="42">
              <template #default="{ row }">
                <div class="object-detail">
                  <div v-if="row.name">
                    <strong>{{ $t("device.messageDataItem") }}</strong
                    >{{ row.name }}
                  </div>
                  <div v-if="row.point">
                    <strong>{{ $t("device.messageRelatedPoint") }}</strong
                    >{{ row.point.name }}（{{ row.point.code }}），
                    {{ $t("device.messagePointAddress") }}
                    {{ row.point.address }}，{{
                      $t("device.messagePointDecodeCode")
                    }}
                    {{ row.point.decode_code }}，
                    {{ $t("device.messagePointCoefficient") }} ×{{
                      row.point.multiplier
                    }}
                    + {{ row.point.addition }}
                  </div>
                  <div v-if="row.decoded_value !== undefined">
                    <strong>{{ $t("device.messageDecodedValue") }}</strong
                    >{{ displayValue(row.decoded_value) }}
                    <span v-if="row.combined_raw"
                      >（{{ $t("device.messageRaw") }}
                      {{ row.combined_raw }}）</span
                    >
                  </div>
                  <div v-if="row.quality">
                    <strong>{{ $t("device.messageQuality") }}</strong
                    >{{ displayValue(row.quality) }}
                  </div>
                  <div v-if="row.timestamp_detail">
                    <strong>{{ $t("device.messageTimestamp") }}</strong
                    >{{ displayValue(row.timestamp_detail) }}
                  </div>
                  <el-table
                    v-if="row.fields?.length"
                    :data="row.fields"
                    size="small"
                    border
                    class="object-fields"
                    highlight-current-row
                    :header-cell-style="{ whiteSpace: 'nowrap' }"
                    @row-click="selectField"
                  >
                    <el-table-column
                      :label="$t('device.messageBytesCol')"
                      width="82"
                    >
                      <template #default="scope">{{
                        byteRange(scope.row.offset, scope.row.length)
                      }}</template>
                    </el-table-column>
                    <el-table-column
                      prop="raw_hex"
                      :label="$t('device.messageRawHex')"
                      min-width="110"
                    />
                    <el-table-column
                      prop="name"
                      :label="$t('device.messageField')"
                      width="130"
                    />
                    <el-table-column
                      prop="display_value"
                      :label="$t('device.messageParsedValue')"
                      min-width="180"
                    />
                  </el-table>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="$t('device.messageIndexCol')" width="55">
              <template #default="{ $index }">{{ $index }}</template>
            </el-table-column>
            <el-table-column :label="$t('device.messageBytesCol')" width="82">
              <template #default="{ row }">{{
                byteRange(row.offset, objectByteLength(row))
              }}</template>
            </el-table-column>
            <el-table-column
              :label="$t('device.messageDataItemCol')"
              min-width="120"
            >
              <template #default="{ row }">
                {{ row.point?.name || "" }}
              </template>
            </el-table-column>
            <el-table-column
              prop="address"
              :label="$t('device.messageAddressIOA')"
              width="120"
            />
            <el-table-column
              :label="$t('device.messageRawValue')"
              min-width="150"
            >
              <template #default="{ row }">
                {{ row.combined_raw || row.raw_value }}
              </template>
            </el-table-column>
            <el-table-column
              :label="$t('device.messageParsedValue')"
              min-width="160"
            >
              <template #default="{ row }">{{
                displayValue(
                  row.decoded_value !== undefined
                    ? row.decoded_value
                    : row.value,
                )
              }}</template>
            </el-table-column>
            <el-table-column
              :label="$t('device.messageEngineeringValue')"
              min-width="130"
            >
              <template #default="{ row }">{{
                displayEngineeringValue(row)
              }}</template>
            </el-table-column>
            <el-table-column
              prop="timestamp"
              :label="$t('device.messageTimestampCol')"
              min-width="150"
            />
          </el-table>
        </section>

        <section v-if="detail.correlation" class="section">
          <h3>{{ $t("device.messageReqResLink") }}</h3>
          <el-descriptions :column="2" border>
            <el-descriptions-item :label="$t('device.messageReqSeqNum')"
              >#{{
                detail.correlation.request_sequence_id
              }}</el-descriptions-item
            >
            <el-descriptions-item :label="$t('device.messageMatchMethod')">{{
              detail.correlation.match_method
            }}</el-descriptions-item>
            <el-descriptions-item :label="$t('device.messageAddressRange')">
              {{ detail.correlation.start_address }} -
              {{ detail.correlation.end_address }}
            </el-descriptions-item>
            <el-descriptions-item :label="$t('device.messageQuantity')">{{
              detail.correlation.quantity
            }}</el-descriptions-item>
          </el-descriptions>
        </section>

        <section v-if="detail.validation.length" class="section">
          <h3>{{ $t("device.messageIntegrityCheck") }}</h3>
          <div
            v-for="item in detail.validation"
            :key="item.name"
            class="validation-item"
          >
            <el-tag :type="item.passed ? 'success' : 'danger'" size="small">{{
              item.passed
                ? $t("device.messagePass")
                : $t("device.messageFailed")
            }}</el-tag>
            <strong>{{ item.name }}</strong
            ><span>{{ item.detail }}</span>
          </div>
        </section>

        <el-alert
          v-for="message in detail.warnings"
          :key="message"
          :title="message"
          type="warning"
          :closable="false"
          class="notice"
        />
        <el-alert
          v-for="message in detail.errors"
          :key="message"
          :title="message"
          type="error"
          :closable="false"
          class="notice"
        />
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { showError } from "@/api/http";
import { Rank } from "@element-plus/icons-vue";
import {
  getMessageDetail,
  type MessageDetail,
  type ParsedObject,
} from "@/api/deviceApi";

const { t } = useI18n();

const props = defineProps<{ deviceName: string }>();
const visible = ref(false);
const loading = ref(false);
const detail = ref<MessageDetail | null>(null);
const selectedField = ref<{ offset: number; length: number } | null>(null);
const rawBytes = computed(
  () => detail.value?.raw_hex.split(/\s+/).filter(Boolean) ?? [],
);
const displayObjects = computed(
  () =>
    detail.value?.objects.filter((object) => !object.covered_by_point) ?? [],
);

async function open(sequenceId: number) {
  visible.value = true;
  loading.value = true;
  detail.value = null;
  selectedField.value = null;
  try {
    detail.value = await getMessageDetail(props.deviceName, sequenceId);
  } catch (error) {
    showError(error, t("device.messageLoadFailed"));
    visible.value = false;
  } finally {
    loading.value = false;
  }
}

function byteRange(offset: number, length: number) {
  return length <= 1 ? `${offset}` : `${offset}-${offset + length - 1}`;
}

function displayValue(value: unknown) {
  return typeof value === "object"
    ? JSON.stringify(value)
    : String(value ?? "");
}

function selectField(field: { offset: number; length: number }) {
  if (!field.length) return;
  selectedField.value = { offset: field.offset, length: field.length };
}

function objectByteLength(object: ParsedObject) {
  const combinedLength =
    object.combined_raw?.trim().split(/\s+/).filter(Boolean).length ?? 0;
  return Math.max(object.length, combinedLength);
}

function selectObject(object: ParsedObject) {
  const length = objectByteLength(object);
  if (typeof object.offset === "number" && length) {
    selectField({ offset: object.offset, length });
    return;
  }
  const mappedFields = object.fields?.filter((field) => field.length > 0) ?? [];
  if (!mappedFields.length) return;
  const start = Math.min(...mappedFields.map((field) => field.offset));
  const end = Math.max(
    ...mappedFields.map((field) => field.offset + field.length),
  );
  selectField({ offset: start, length: end - start });
}

function handleObjectRowClick(
  object: ParsedObject,
  _column: unknown,
  event: MouseEvent,
) {
  if ((event.target as HTMLElement | null)?.closest(".object-fields")) return;
  selectObject(object);
}

function isSelectedByte(index: number) {
  const selected = selectedField.value;
  return (
    !!selected &&
    index >= selected.offset &&
    index < selected.offset + selected.length
  );
}

function displayEngineeringValue(row: Record<string, any>) {
  if (row.engineering_value === undefined) return row.point?.name ? "—" : "";
  const pointName = row.point?.name ? `${row.point.name}: ` : "";
  return `${pointName}${displayValue(row.engineering_value)}`;
}

defineExpose({ open });
</script>

<style scoped>
.drawer-title-content {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.resize-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: none;
  padding: 3px 7px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  cursor: help;
}
.resize-hint .el-icon {
  font-size: 14px;
  color: var(--el-color-primary);
}
.detail-body {
  min-height: 180px;
}
.section {
  margin-top: 18px;
}
.section h3 {
  margin: 0 0 10px;
  font-size: 15px;
}
.raw-frame {
  padding: 14px;
  border-radius: 6px;
  background: #111827;
  color: #d1fae5;
  font:
    13px/1.8 Consolas,
    Monaco,
    monospace;
  word-break: break-all;
  white-space: normal;
}
.raw-byte {
  display: inline-block;
  margin-right: 7px;
  padding: 0 2px;
  border-radius: 3px;
  transition:
    background-color 0.15s,
    color 0.15s;
}
.raw-byte.selected {
  background: #f59e0b;
  color: #111827;
  font-weight: 700;
}
.raw-hint {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.validation-item {
  display: grid;
  grid-template-columns: 54px 110px 1fr;
  align-items: center;
  gap: 8px;
  margin: 7px 0;
  font-size: 13px;
}
.notice {
  margin-top: 8px;
}
.object-detail {
  padding: 8px 14px 14px;
  line-height: 1.8;
}
.object-fields {
  margin-top: 8px;
}

:global(.message-detail-drawer.rtl > .el-drawer__dragger) {
  left: -7px;
  width: 14px;
}

:global(.message-detail-drawer.rtl > .el-drawer__dragger::after) {
  content: "⠿";
  position: absolute;
  top: 50%;
  left: 50%;
  display: grid;
  place-items: center;
  width: 22px;
  height: 48px;
  border: 1px solid var(--el-border-color);
  border-radius: 7px;
  background: var(--el-bg-color);
  box-shadow: var(--el-box-shadow-light);
  color: var(--el-text-color-secondary);
  font-size: 18px;
  line-height: 1;
  transform: translate(-50%, -50%);
  pointer-events: none;
}

:global(.message-detail-drawer.rtl > .el-drawer__dragger:hover::after) {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
</style>
