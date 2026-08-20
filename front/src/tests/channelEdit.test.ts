/// <reference types="jest" />

import {
  applyConnectionTypeDefaults,
  applyProtocolTypeDefaults,
  shouldSaveChannelSecurity,
} from "@/utils/channelEdit";
import type { ChannelCreateRequest, ProtocolOption } from "@/types/channel";

const unchangedEdit = {
  isEdit: true,
  tlsSupported: true,
  tlsEnabled: false,
  tlsMode: "mutual" as const,
  originalTlsEnabled: false,
  originalTlsMode: "mutual" as const,
  hasNewFiles: false,
};

describe("channel edit optimization", () => {
  it("skips unchanged TLS settings", () => {
    expect(shouldSaveChannelSecurity(unchangedEdit)).toBe(false);
  });

  it("saves changed TLS settings or certificate files", () => {
    expect(
      shouldSaveChannelSecurity({ ...unchangedEdit, tlsEnabled: true }),
    ).toBe(true);
    expect(
      shouldSaveChannelSecurity({ ...unchangedEdit, hasNewFiles: true }),
    ).toBe(true);
  });

  it("never saves TLS for unsupported protocols", () => {
    expect(
      shouldSaveChannelSecurity({
        ...unchangedEdit,
        tlsSupported: false,
        tlsEnabled: true,
        hasNewFiles: true,
      }),
    ).toBe(false);
  });
});

describe("channel edit endpoint hydration", () => {
  const protocols: ProtocolOption[] = [
    { value: 2, label: "IEC104", conn_types: [1, 2] },
  ];

  const createForm = (): ChannelCreateRequest => ({
    code: "iec104-client",
    name: "iec104-client",
    protocol_type: 2,
    conn_type: 1,
    ip: "10.20.30.40",
    port: 12404,
  });

  it("preserves persisted IP and port while channel details are hydrating", () => {
    const form = createForm();

    applyProtocolTypeDefaults(form, protocols, 2, true);
    applyConnectionTypeDefaults(form, 1, true);

    expect(form.ip).toBe("10.20.30.40");
    expect(form.port).toBe(12404);
  });

  it("still applies defaults for an explicit user connection-mode change", () => {
    const form = createForm();

    applyConnectionTypeDefaults(form, 1);

    expect(form.ip).toBe("127.0.0.1");
  });
});
