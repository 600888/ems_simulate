/// <reference types="jest" />

import {
  CONN_TYPE,
  isSerialConnectionType,
  PROTOCOL_TYPE,
  supportsTlsProtocol,
} from "@/constants/protocol";

describe("protocol connection type", () => {
  it("recognizes both serial roles independently of protocol", () => {
    expect(isSerialConnectionType(CONN_TYPE.SERIAL_MASTER)).toBe(true);
    expect(isSerialConnectionType(CONN_TYPE.SERIAL_SLAVE)).toBe(true);
  });

  it("does not treat TCP roles or missing values as serial", () => {
    expect(isSerialConnectionType(CONN_TYPE.TCP_CLIENT)).toBe(false);
    expect(isSerialConnectionType(CONN_TYPE.TCP_SERVER)).toBe(false);
    expect(isSerialConnectionType(null)).toBe(false);
    expect(isSerialConnectionType(undefined)).toBe(false);
  });
});

describe("protocol TLS support", () => {
  it("includes DNP3 and excludes serial-only protocols", () => {
    expect(supportsTlsProtocol(PROTOCOL_TYPE.DNP3)).toBe(true);
    expect(supportsTlsProtocol(PROTOCOL_TYPE.DLT645)).toBe(false);
  });
});
