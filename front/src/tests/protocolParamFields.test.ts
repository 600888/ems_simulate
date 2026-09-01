/// <reference types="jest" />

// @ts-ignore The application tsconfig intentionally excludes Node globals.
import { readFileSync } from "node:fs";

const componentSource = readFileSync(
  "src/components/device/DeviceProtocolParams.vue",
  "utf8",
);

function fieldBlock(name: string, nextName: string): string {
  const start = componentSource.indexOf(`const ${name}: FieldDefinition[] = [`);
  const end = componentSource.indexOf(
    `const ${nextName}: FieldDefinition[] = [`,
    start,
  );
  expect(start).toBeGreaterThanOrEqual(0);
  expect(end).toBeGreaterThan(start);
  return componentSource.slice(start, end);
}

describe("protocol parameter field ownership", () => {
  it("keeps DNP3 client-only fields out of Modbus and in the DNP3 client form", () => {
    const modbusFields = fieldBlock("modbusClient", "modbusServer");
    const dnp3Fields = fieldBlock("dnp3Client", "dnp3Server");
    const dnp3ClientOnlyKeys = [
      "time_sync_enabled",
      "enable_unsolicited",
      "event_interval_s",
      "cache_ttl_ms",
      "link_confirm",
      "link_confirm_timeout_ms",
      "link_confirm_max_retries",
    ];

    for (const key of dnp3ClientOnlyKeys) {
      expect(modbusFields).not.toContain(`key: "${key}"`);
      expect(dnp3Fields).toContain(`key: "${key}"`);
    }
  });
});
