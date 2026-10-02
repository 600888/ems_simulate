import type { OpcUaDeviceConfig } from "@/types/channel";

export function defaultOpcUaDeviceConfig(): OpcUaDeviceConfig {
  return {
    endpoint_path: "/ems/",
    namespace_uri: "",
    mode: "None",
    policy: "Basic256Sha256",
    application_uri: "urn:ems-simulate:application",
    advertised_host: null,
    identity: "anonymous",
    username: "",
    allow_anonymous: false,
    generate_certificate: true,
  };
}

/** Only request fields enter the payload; public flags and persisted secrets stay out. */
export function opcuaDeviceConfigPayload(
  config: OpcUaDeviceConfig,
): OpcUaDeviceConfig {
  return {
    endpoint_path: config.endpoint_path.trim(),
    namespace_uri: config.namespace_uri.trim(),
    mode: config.mode,
    policy: config.policy,
    application_uri: config.application_uri.trim(),
    advertised_host: config.advertised_host?.trim() || null,
    identity: config.mode === "None" ? "anonymous" : config.identity,
    username: config.username.trim(),
    allow_anonymous: config.allow_anonymous,
    generate_certificate:
      config.mode !== "None" && !!config.generate_certificate,
  };
}

export function opcuaDeviceConfigError(
  config: OpcUaDeviceConfig,
  connType: number,
): string | null {
  if (
    !/^\/[^?#\\]*$/.test(config.endpoint_path.trim()) ||
    config.endpoint_path.length > 255
  )
    return "opcua.deviceEndpointPathError";
  if (config.mode !== "None" && !config.application_uri.trim())
    return "opcua.deviceApplicationUriRequired";
  if (
    connType === 1 &&
    config.identity === "username" &&
    (config.mode !== "SignAndEncrypt" || !config.username.trim())
  )
    return "opcua.deviceUsernameRequiresEncryption";
  return null;
}

export async function opcuaFileBase64(file: File): Promise<string> {
  if (!file.size || file.size > 24 * 1024)
    throw new Error("opcua.deviceCertificateSizeError");
  const bytes = new Uint8Array(await file.arrayBuffer());
  return btoa(Array.from(bytes, (byte) => String.fromCharCode(byte)).join(""));
}
