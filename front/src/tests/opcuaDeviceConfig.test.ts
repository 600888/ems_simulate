import {
  defaultOpcUaDeviceConfig,
  opcuaDeviceConfigPayload,
  opcuaDeviceConfigError,
} from "@/utils/opcuaDeviceConfig";

test("edit submits configuration without public flags or persisted credentials", () => {
  const config = {
    ...defaultOpcUaDeviceConfig(),
    mode: "SignAndEncrypt" as const,
    generate_certificate: false,
    certificate_configured: true,
    private_key_configured: true,
    password_configured: true,
    trusted_count: 2,
    password: "never-resubmit",
    private_key: "secret",
  };
  const payload = opcuaDeviceConfigPayload(config);
  expect(payload.mode).toBe("SignAndEncrypt");
  expect(payload.generate_certificate).toBe(false);
  for (const key of [
    "certificate_configured",
    "private_key_configured",
    "password_configured",
    "trusted_count",
    "password",
    "private_key",
  ])
    expect(payload).not.toHaveProperty(key);
});

test("disabling security submits anonymous identity without generating a certificate", () => {
  const config = {
    ...defaultOpcUaDeviceConfig(),
    identity: "username" as const,
    username: "operator",
  };
  const payload = opcuaDeviceConfigPayload(config);
  expect(payload.identity).toBe("anonymous");
  expect(payload.generate_certificate).toBe(false);
});

test("OPC UA path and username encryption constraints are validated", () => {
  const config = defaultOpcUaDeviceConfig();
  expect(opcuaDeviceConfigError(config, 1)).toBeNull();
  config.endpoint_path = "invalid?path";
  expect(opcuaDeviceConfigError(config, 1)).toBe(
    "opcua.deviceEndpointPathError",
  );
  config.endpoint_path = "/ems/";
  config.mode = "Sign";
  config.identity = "username";
  config.username = "operator";
  expect(opcuaDeviceConfigError(config, 1)).toBe(
    "opcua.deviceUsernameRequiresEncryption",
  );
  config.mode = "SignAndEncrypt";
  expect(opcuaDeviceConfigError(config, 1)).toBeNull();
});
