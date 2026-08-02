/// <reference types="jest" />

import { shouldSaveChannelSecurity } from "@/utils/channelEdit";

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
