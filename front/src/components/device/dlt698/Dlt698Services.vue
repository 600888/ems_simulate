<template>
  <div>
    <template v-if="tab === 'reports'">
      <h3>
        {{
          role === "client"
            ? l("上报接收", "Received reports")
            : l("主动上报", "Send reports")
        }}
      </h3>
      <el-alert
        :title="
          l(
            '保留来源会话、PIID-ACD、原始内容与确认状态；FollowReport / ACD 由运行时处理。',
            'Retains session, PIID-ACD, payload and acknowledgement; runtime handles FollowReport / ACD.',
          )
        "
        type="info"
        :closable="false"
      />
      <div class="actions">
        <el-button
          :disabled="!can('reports') || busy"
          @click="emit('refresh-reports')"
          >{{ l("刷新上报", "Refresh reports") }}</el-button
        ><el-button
          v-if="role === 'server'"
          type="primary"
          :disabled="
            busy || (!preview && (!can('reports') || !associated.length))
          "
          @click="reportOpen = true"
          >{{
            preview
              ? l("上报表单预览", "Preview report form")
              : l("发送上报", "Send report")
          }}</el-button
        >
      </div>
      <el-table :data="reports" border stripe
        ><el-table-column
          prop="time"
          :label="l('时间', 'Time')"
          min-width="190" /><el-table-column
          prop="session_id"
          :label="l('来源会话', 'Session')"
          min-width="140" /><el-table-column
          prop="kind"
          :label="l('类型', 'Type')"
          width="110" /><el-table-column
          prop="piid_acd"
          label="PIID-ACD"
          width="100" /><el-table-column
          prop="oad"
          label="OAD"
          width="110" /><el-table-column
          :label="l('原始内容', 'Payload')"
          min-width="160"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="inspectedReport = row">{{
              row.data ? dataText(row.data) : l("查看详情", "View details")
            }}</el-button></template
          ></el-table-column
        ><el-table-column
          prop="acknowledgement"
          :label="l('确认状态', 'Acknowledgement')"
          min-width="140"
      /></el-table>
    </template>
    <template v-else>
      <h3>
        {{
          role === "client"
            ? l("代理服务", "Proxy services")
            : l("代理路由", "Proxy routes")
        }}
      </h3>
      <template v-if="role === 'client'">
        <el-form label-width="160px" @submit.prevent="executeProxy">
          <el-form-item :label="l('代理服务类型', 'Proxy service')"
            ><el-select
              v-model="proxyService"
              style="width: 100%"
              @change="resetItems"
              ><el-option
                v-for="service in proxyServices"
                :key="service"
                :value="service"
                :label="service" /></el-select
          ></el-form-item>
          <el-form-item
            v-if="proxyService !== 'TransCommand'"
            :label="l('目标 TSA', 'Target TSAs')"
            ><el-input
              v-model="tsaText"
              type="textarea"
              :rows="2"
              :placeholder="
                l(
                  '每行一个 single TSA，保留顺序和重复项',
                  'One single TSA per line; retain order and duplicates',
                )
              "
          /></el-form-item>
          <el-form-item
            v-if="proxyService === 'GetRecord'"
            :label="l('记录查询参数', 'Record query')"
            ><el-input v-model="queryText" type="textarea" :rows="8"
          /></el-form-item>
          <template v-else-if="proxyService === 'TransCommand'">
            <el-form-item :label="l('透明端口 OAD', 'Transparent port OAD')"
              ><el-input v-model="portOad" /></el-form-item
            ><el-form-item :label="l('命令字节 HEX', 'Command bytes HEX')"
              ><el-input
                v-model="commandHex"
                type="textarea"
                :rows="2"
                placeholder="68 01 02 03 16"
            /></el-form-item>
            <el-form-item :label="l('响应超时 (s)', 'Response timeout (s)')"
              ><el-input-number
                v-model="responseTimeout"
                :min="1"
                :max="65535" /></el-form-item
            ><el-form-item :label="l('字节超时 (ms)', 'Byte timeout (ms)')"
              ><el-input-number v-model="byteTimeout" :min="1" :max="65535"
            /></el-form-item>
            <el-form-item :label="l('串口通信参数', 'Serial parameters')"
              ><el-input v-model="communicationText" type="textarea" :rows="5"
            /></el-form-item>
            <el-alert
              :title="
                l(
                  '透明端口是 OAD；通信参数由后端映射为 COMDCB。需要真实透明桥后端。',
                  'Port is an OAD. Backend maps serial parameters to COMDCB; a real transparent bridge is required.',
                )
              "
              type="info"
              :closable="false"
            />
          </template>
          <template v-else
            ><el-form-item
              :label="l('有序请求项 JSON', 'Ordered request items')"
              ><el-input
                v-model="itemsText"
                type="textarea"
                :rows="7" /></el-form-item
            ><small>{{
              l(
                "GET: oad；SET: oad + data；ACTION: omd + data；ThenGet 另填 get_oad、delay_s。每个 TSA 按顺序执行，保留重复项。",
                "GET: oad; SET: oad + data; ACTION: omd + data. ThenGet also needs get_oad and delay_s. Each TSA retains item order and duplicates.",
              )
            }}</small></template
          >
          <div class="actions">
            <el-button
              type="primary"
              :disabled="!can('proxy') || busy"
              @click="executeProxy"
              >{{ l("执行一次", "Execute once") }}</el-button
            >
          </div>
        </el-form>
        <el-divider>{{ l("高级服务", "Advanced services") }}</el-divider>
        <el-form label-width="160px"
          ><el-form-item label="GET MD5 · OAD"
            ><el-input v-model="md5Oad" /><el-button
              :disabled="!can('md5') || busy"
              @click="executeMd5"
              >GET MD5</el-button
            ></el-form-item
          ><el-form-item label="ThenGet"
            ><el-radio-group v-model="thenGetMode" @change="resetThenItems"
              ><el-radio value="set">SET ThenGet</el-radio
              ><el-radio value="action"
                >ACTION ThenGet</el-radio
              ></el-radio-group
            ></el-form-item
          ><el-form-item :label="l('有序请求项 JSON', 'Ordered request items')"
            ><el-input
              v-model="thenItemsText"
              type="textarea"
              :rows="6" /></el-form-item
          ><el-form-item
            ><el-button
              :disabled="!can('then_get') || busy"
              @click="executeThenGet"
              >{{ l("执行 ThenGet 一次", "Execute ThenGet once") }}</el-button
            ></el-form-item
          ></el-form
        >
      </template>
      <template v-else
        ><el-form inline @submit.prevent="bindRoute"
          ><el-form-item label="TSA"
            ><el-input v-model="routeTsa" /></el-form-item
          ><el-form-item :label="l('已关联会话', 'Associated session')"
            ><el-select v-model="sessionId" style="width: 220px"
              ><el-option
                v-for="session in associated"
                :key="session.id"
                :value="session.id"
                :label="`${session.id} · ${session.address}`" /></el-select></el-form-item
          ><el-form-item
            ><el-button
              type="primary"
              :disabled="!can('routes') || !sessionId || busy"
              @click="bindRoute"
              >{{ l("绑定路由", "Bind route") }}</el-button
            ></el-form-item
          ></el-form
        ><el-table :data="routes" border stripe
          ><el-table-column prop="tsa" label="TSA" /><el-table-column
            prop="session_id"
            :label="l('会话', 'Session')" /><el-table-column
            prop="bridge"
            :label="l('透明桥状态', 'Transparent bridge')" /></el-table
        ><el-alert
          :title="
            l(
              '路由目标必须已关联；透明桥状态由真实后端连接决定。',
              'Routes require an associated target; real backend connections determine bridge state.',
            )
          "
          type="info"
          :closable="false"
      /></template>
    </template>
    <el-alert
      v-if="error || localError"
      :title="error || localError"
      type="error"
      :closable="false"
      class="result"
    />
    <el-alert
      v-if="results.some((r) => r.kind === 'unknown')"
      :title="
        l(
          '执行结果未知；写入、方法及 ThenGet 不自动重试。',
          'Outcome unknown; writes, methods and ThenGet never auto retry.',
        )
      "
      type="warning"
      :closable="false"
      class="result"
    />
    <el-table
      v-if="results.length"
      :data="flatResults"
      border
      stripe
      class="result"
      ><el-table-column
        prop="path"
        :label="l('请求序号', 'Request index')"
        width="100" /><el-table-column
        prop="tsa"
        label="TSA"
        min-width="110" /><el-table-column
        prop="oad"
        label="OAD / OMD"
        min-width="110" /><el-table-column
        :label="l('结果', 'Result')"
        min-width="140"
        ><template #default="{ row }"
          ><el-tag
            :type="
              row.kind === 'data' || row.dar === 0
                ? 'success'
                : row.kind === 'unknown'
                  ? 'warning'
                  : 'info'
            "
            >{{
              row.dar === 0
                ? l("成功 · DAR = 0", "Success · DAR = 0")
                : row.kind
            }}</el-tag
          ></template
        ></el-table-column
      ><el-table-column prop="dar" label="DAR" width="70" /><el-table-column
        label="Data / MD5"
        min-width="170"
        ><template #default="{ row }"
          ><el-popover v-if="row.data" trigger="click" width="400"
            ><template #reference
              ><el-button link>{{ dataText(row.data) }}</el-button></template
            ><Dlt698DataTree :data="row.data" /></el-popover
          ><code v-else>{{ row.md5 || "—" }}</code></template
        ></el-table-column
      ><el-table-column
        prop="message"
        :label="l('详情', 'Detail')"
        min-width="160"
    /></el-table>
    <el-dialog
      v-model="reportOpen"
      :title="l('主动上报参数', 'Report parameters')"
      width="740px"
      :close-on-click-modal="false"
    >
      <el-form label-width="140px" @submit.prevent="sendReport"
        ><el-form-item :label="l('关联会话', 'Session')"
          ><el-select v-model="sessionId"
            ><el-option
              v-for="session in associated"
              :key="session.id"
              :label="session.id"
              :value="session.id" /></el-select></el-form-item
        ><el-form-item :label="l('上报类型', 'Report type')"
          ><el-select v-model="reportKind"
            ><el-option
              v-for="kind in reportKinds"
              :key="kind.value"
              :value="kind.value"
              :label="l(kind.zh, kind.en)" /></el-select
        ></el-form-item>
        <template v-if="reportKind === 'normal'"
          ><el-form-item label="OAD"
            ><el-input v-model="reportOad" /></el-form-item
          ><el-form-item label="Data"
            ><Dlt698DataEditor
              v-model="reportData"
              @valid="reportDataValid = $event" /></el-form-item
        ></template>
        <el-form-item
          v-else-if="reportKind === 'list'"
          :label="l('有序属性 JSON', 'Ordered attributes')"
          ><el-input
            v-model="reportItemsText"
            type="textarea"
            :rows="7" /></el-form-item
        ><el-form-item
          v-else-if="reportKind === 'record'"
          :label="l('记录内容 JSON', 'Record payload')"
          ><el-input v-model="reportRecordText" type="textarea" :rows="9"
        /></el-form-item>
        <template v-else
          ><el-form-item :label="l('透明端口 OAD', 'Transparent port OAD')"
            ><el-input v-model="reportPort" /></el-form-item
          ><el-form-item :label="l('透明字节帧', 'Transparent byte frames')"
            ><el-input
              v-model="reportFrames"
              type="textarea"
              :rows="4"
              :placeholder="
                l('每行一帧十六进制字节', 'One hex byte frame per line')
              " /></el-form-item
        ></template>
      </el-form>
      <el-alert
        v-if="preview"
        :title="
          l('表单预览，不会发送上报。', 'Form preview; no report is sent.')
        "
        type="info"
        :closable="false"
      /><el-alert
        v-if="error || localError"
        :title="error || localError"
        type="error"
        :closable="false"
      />
      <template #footer
        ><el-button @click="reportOpen = false">{{
          l("关闭", "Close")
        }}</el-button
        ><el-button
          type="primary"
          :disabled="
            preview ||
            busy ||
            !can('reports') ||
            !sessionId ||
            (reportKind === 'normal' && !reportDataValid)
          "
          @click="sendReport"
          >{{ l("发送一次", "Send once") }}</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      :model-value="!!inspectedReport"
      :title="l('上报原始详情', 'Original report details')"
      width="740px"
      @update:model-value="inspectedReport = undefined"
      ><Dlt698DataTree
        v-if="inspectedReport?.data"
        :data="inspectedReport.data"
      />
      <pre>{{ JSON.stringify(inspectedReport, null, 2) }}</pre>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from "vue";
import type {
  Dlt698Data,
  Dlt698Feature,
  Dlt698Operation,
  Dlt698RecordQuery,
  Dlt698Report,
  Dlt698Result,
  Dlt698Role,
  Dlt698Route,
  Dlt698Status,
} from "@/types/dlt698";
import {
  dataText,
  normalizeOad,
  validateData,
  validateRecordQuery,
} from "@/utils/dlt698";
import { useDlt698Text } from "@/composables/useDlt698Text";
import Dlt698DataEditor from "./Dlt698DataEditor.vue";
import Dlt698DataTree from "./Dlt698DataTree.vue";
const props = defineProps<{
  tab: string;
  role: Dlt698Role;
  can: (feature: Dlt698Feature) => boolean;
  sessions: Dlt698Status["sessions"];
  reports: Dlt698Report[];
  routes: Dlt698Route[];
  results: Dlt698Result[];
  error: string;
  busy: boolean;
  preview?: boolean;
}>();
const emit = defineEmits<{
  (e: "refresh-reports"): void;
  (e: "operation", request: Dlt698Operation): void;
  (e: "route", route: Dlt698Route): void;
}>();
const l = useDlt698Text();
const proxyServices = [
  "GetRequestList",
  "GetRecord",
  "SetRequestList",
  "SetThenGetRequestList",
  "ActionRequestList",
  "ActionThenGetRequestList",
  "TransCommand",
];
const proxyService = ref("GetRequestList"),
  tsaText = ref(""),
  sessionId = ref(""),
  routeTsa = ref(""),
  localError = ref("");
const itemsText = ref('[{"oad":"20000201"}]'),
  thenGetMode = ref<"set" | "action">("set"),
  thenItemsText = ref(
    '[{"oad":"F0010200","data":{"type":"UInt16","value":"0"},"get_oad":"F0010200","delay_s":0}]',
  ),
  md5Oad = ref("20000201");
const queryText = ref(
  JSON.stringify(
    {
      template: "daily",
      oad: "50040200",
      selector: "all",
      start: "",
      end: "",
      latest: 1,
      columns: ["20210200", "00100201"],
    },
    null,
    2,
  ),
);
const portOad = ref("F2010200"),
  commandHex = ref(""),
  responseTimeout = ref(5),
  byteTimeout = ref(100),
  communicationText = ref(
    JSON.stringify(
      {
        baud_rate: 9600,
        data_bits: 8,
        stop_bits: 1,
        parity: "E",
        flow_control: "none",
      },
      null,
      2,
    ),
  );
const reportOpen = ref(false),
  reportKind = ref("normal"),
  reportOad = ref("20000201"),
  reportDataValid = ref(true),
  reportPort = ref("F2010200"),
  reportFrames = ref("");
const reportData = ref<Dlt698Data>({ type: "UInt16", value: "2301" }),
  reportItemsText = ref(
    '[{"oad":"20000201","data":{"type":"UInt16","value":"2301"}}]',
  );
const reportRecordText = ref(
  JSON.stringify(
    {
      oad: "50040200",
      columns: ["20210200", "00100201"],
      rows: [
        [
          { type: "DateTimeS", value: "2026-10-14T00:00:00" },
          { type: "UInt32", value: "123456" },
        ],
      ],
    },
    null,
    2,
  ),
);
const inspectedReport = ref<Dlt698Report>(),
  associated = computed(() =>
    props.sessions.filter((session) => session.associated),
  );
const reportKinds = [
  { value: "normal", zh: "普通上报", en: "Normal report" },
  { value: "list", zh: "列表上报", en: "List report" },
  { value: "record", zh: "记录上报", en: "Record report" },
  { value: "transparent", zh: "透明上报", en: "Transparent report" },
];
const flatResults = computed(() => {
  const rows: (Dlt698Result & { path: string })[] = [];
  function visit(results: Dlt698Result[], prefix = "", inheritedTsa = "") {
    results.forEach((result) => {
      const path = prefix ? `${prefix}.${result.index}` : String(result.index);
      rows.push({ ...result, tsa: result.tsa || inheritedTsa, path });
      if (result.children)
        visit(result.children, path, result.tsa || inheritedTsa);
    });
  }
  visit(props.results);
  return rows;
});
function attempt(action: () => void) {
  localError.value = "";
  try {
    action();
  } catch (e) {
    localError.value = (e as Error).message;
  }
}
function singleTsa(input: string) {
  const tsa = input.replace(/\s/g, "").toUpperCase();
  if (!/^(?:[0-9A-F]{2}){1,16}$/.test(tsa))
    throw new Error(
      l(
        "TSA 需为 1–16 个地址字节，使用 single 地址",
        "TSA requires 1–16 single-address bytes",
      ),
    );
  return tsa;
}
function hex(input: string) {
  const bytes = input.replace(/\s/g, "").toUpperCase();
  if (!/^(?:[0-9A-F]{2})+$/.test(bytes))
    throw new Error(
      l(
        "请输入非空十六进制字节对",
        "Nonempty hexadecimal byte pairs are required",
      ),
    );
  return bytes;
}
function parseItems(
  text: string,
  method: boolean,
  withData: boolean,
  thenGet = false,
): Dlt698Operation["items"] {
  const entries = JSON.parse(text);
  if (!Array.isArray(entries) || !entries.length)
    throw new Error(
      l("请求项必须为非空数组", "Request items must be a nonempty array"),
    );
  return entries.map((entry) => {
    if (!entry || typeof entry !== "object")
      throw new Error("Invalid request item");
    const item: Dlt698Operation["items"][number] = {
      [method ? "omd" : "oad"]: normalizeOad(
        entry[method ? "omd" : "oad"] || "",
      ),
    };
    if (withData) {
      validateData(entry.data);
      item.data = entry.data;
    }
    if (thenGet) {
      item.get_oad = normalizeOad(entry.get_oad || "");
      if (
        !Number.isInteger(entry.delay_s) ||
        entry.delay_s < 0 ||
        entry.delay_s > 255
      )
        throw new Error("delay_s: 0–255");
      item.delay_s = entry.delay_s;
    }
    return item;
  });
}
function resetItems() {
  const method = proxyService.value.startsWith("Action"),
    thenGet = proxyService.value.includes("ThenGet"),
    withData = !proxyService.value.startsWith("Get");
  itemsText.value = JSON.stringify(
    [
      {
        [method ? "omd" : "oad"]: method
          ? "F0010100"
          : withData
            ? "F0010200"
            : "20000201",
        ...(withData ? { data: { type: "UInt16", value: "0" } } : {}),
        ...(thenGet ? { get_oad: "F0010200", delay_s: 0 } : {}),
      },
    ],
    null,
    2,
  );
  localError.value = "";
}
function resetThenItems() {
  thenItemsText.value = JSON.stringify(
    [
      {
        [thenGetMode.value === "action" ? "omd" : "oad"]:
          thenGetMode.value === "action" ? "F0010100" : "F0010200",
        data: { type: "UInt16", value: "0" },
        get_oad: "F0010200",
        delay_s: 0,
      },
    ],
    null,
    2,
  );
}
function executeProxy() {
  if (!props.can("proxy") || props.busy) return;
  attempt(() => {
    const request: Dlt698Operation = {
      service: "proxy",
      proxy_service: proxyService.value,
      items: [],
    };
    if (proxyService.value === "TransCommand") {
      const communication = JSON.parse(communicationText.value);
      if (
        !Number.isInteger(communication.baud_rate) ||
        communication.baud_rate <= 0 ||
        ![5, 6, 7, 8].includes(communication.data_bits) ||
        ![1, 2].includes(communication.stop_bits) ||
        !["N", "E", "O"].includes(communication.parity) ||
        !["none", "hardware", "software"].includes(communication.flow_control)
      )
        throw new Error(l("串口通信参数不合法", "Invalid serial parameters"));
      if (
        !Number.isInteger(responseTimeout.value) ||
        responseTimeout.value < 1 ||
        responseTimeout.value > 65535 ||
        !Number.isInteger(byteTimeout.value) ||
        byteTimeout.value < 1 ||
        byteTimeout.value > 65535
      )
        throw new Error("Invalid timeout");
      request.options = {
        port: normalizeOad(portOad.value),
        bytes: hex(commandHex.value),
        response_timeout_s: responseTimeout.value,
        byte_timeout_ms: byteTimeout.value,
        communication,
      };
      request.items = [{ oad: normalizeOad(portOad.value) }];
    } else {
      const targets = tsaText.value
        .split("\n")
        .map((v) => v.trim())
        .filter(Boolean)
        .map(singleTsa);
      if (!targets.length)
        throw new Error(l("请填写目标 TSA", "Target TSA is required"));
      if (proxyService.value === "GetRecord") {
        const query: Dlt698RecordQuery = JSON.parse(queryText.value);
        validateRecordQuery(query);
        request.options = { query };
        request.items = targets.map((tsa) => ({
          tsa,
          oad: normalizeOad(query.oad),
        }));
      } else {
        const items = parseItems(
          itemsText.value,
          proxyService.value.startsWith("Action"),
          !proxyService.value.startsWith("Get"),
          proxyService.value.includes("ThenGet"),
        );
        request.items = targets.flatMap((tsa) =>
          items.map((item) => ({ ...item, tsa })),
        );
      }
    }
    emit("operation", request);
  });
}
function executeMd5() {
  if (props.can("md5") && !props.busy)
    attempt(() =>
      emit("operation", {
        service: "md5",
        items: [{ oad: normalizeOad(md5Oad.value) }],
      }),
    );
}
function executeThenGet() {
  if (props.can("then_get") && !props.busy)
    attempt(() =>
      emit("operation", {
        service: "then_get",
        items: parseItems(
          thenItemsText.value,
          thenGetMode.value === "action",
          true,
          true,
        ),
        options: { operation: thenGetMode.value },
      }),
    );
}
function bindRoute() {
  if (!props.can("routes") || props.busy) return;
  attempt(() => {
    if (!associated.value.some((s) => s.id === sessionId.value))
      throw new Error(l("请选择已关联会话", "Select an associated session"));
    emit("route", {
      tsa: singleTsa(routeTsa.value),
      session_id: sessionId.value,
      bridge: "unavailable",
    });
  });
}
function sendReport() {
  if (props.preview || !props.can("reports") || props.busy) return;
  attempt(() => {
    if (!associated.value.some((s) => s.id === sessionId.value))
      throw new Error(l("请选择已关联会话", "Select an associated session"));
    const request: Dlt698Operation = {
      service: "report",
      session_id: sessionId.value,
      items: [],
      options: { report_kind: reportKind.value },
    };
    if (reportKind.value === "normal") {
      if (!reportDataValid.value) return;
      validateData(reportData.value);
      request.items = [
        { oad: normalizeOad(reportOad.value), data: reportData.value },
      ];
    } else if (reportKind.value === "list")
      request.items = parseItems(reportItemsText.value, false, true);
    else if (reportKind.value === "record") {
      const record = JSON.parse(reportRecordText.value);
      record.oad = normalizeOad(record.oad || "");
      if (
        !Array.isArray(record.columns) ||
        !record.columns.length ||
        !Array.isArray(record.rows)
      )
        throw new Error("Invalid record columns / rows");
      record.columns = record.columns.map(normalizeOad);
      record.rows.forEach((row: Dlt698Data[]) => {
        if (!Array.isArray(row) || row.length !== record.columns.length)
          throw new Error("Record column count mismatch");
        row.forEach(validateData);
      });
      request.options!.record = record;
      request.items = [{ oad: record.oad }];
    } else {
      const frames = reportFrames.value
        .split("\n")
        .map((v) => v.trim())
        .filter(Boolean)
        .map(hex);
      if (!frames.length)
        throw new Error(l("请输入透明帧", "Transparent frames are required"));
      request.options!.port = normalizeOad(reportPort.value);
      request.options!.frames = frames;
    }
    emit("operation", request);
  });
}
</script>
<style scoped>
h3 {
  margin: 0 0 16px;
}
.actions {
  display: flex;
  gap: 12px;
  margin: 16px 0;
  flex-wrap: wrap;
}
.result {
  margin-top: 16px;
}
small {
  color: var(--text-secondary);
  display: block;
  margin: 12px 0;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 500px;
  overflow: auto;
  background: var(--bg-subtle);
  padding: 12px;
}
</style>
