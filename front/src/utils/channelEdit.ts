import {
  PROTOCOL_DEFAULT_CLIENT_IP,
  PROTOCOL_DEFAULT_PORTS,
} from "@/constants/protocol";
import type { ChannelCreateRequest, ProtocolOption } from "@/types/channel";

export interface SecuritySaveState {
  isEdit: boolean;
  tlsSupported: boolean;
  tlsEnabled: boolean;
  tlsMode: "one_way" | "mutual";
  originalTlsEnabled: boolean;
  originalTlsMode: "one_way" | "mutual";
  hasNewFiles: boolean;
}

export interface TlsMaterialRequirements {
  identity: boolean;
  caCertificate: boolean;
}

/** Required files for one-way TLS and mutual TLS, based on endpoint role. */
export function getTlsMaterialRequirements(
  tlsMode: "one_way" | "mutual",
  connType: number,
): TlsMaterialRequirements {
  return {
    identity: tlsMode === "mutual" || connType === 2,
    caCertificate: tlsMode === "mutual" || connType === 1,
  };
}

/** Avoid saving/reloading TLS when an edit did not change its configuration. */
export function shouldSaveChannelSecurity(state: SecuritySaveState): boolean {
  if (!state.tlsSupported) return false;
  const settingsChanged =
    state.tlsEnabled !== state.originalTlsEnabled ||
    state.tlsMode !== state.originalTlsMode;
  return (
    state.hasNewFiles || settingsChanged || (!state.isEdit && state.tlsEnabled)
  );
}

/**
 * Apply defaults after the user changes the protocol.
 *
 * Detail hydration also changes the reactive protocol field, so it must not
 * reuse the user-change defaults or the persisted endpoint will be overwritten.
 */
export function applyProtocolTypeDefaults(
  form: ChannelCreateRequest,
  protocols: ProtocolOption[],
  newType: number,
  hydrating = false,
): void {
  if (hydrating) return;

  const defaultPort = PROTOCOL_DEFAULT_PORTS[newType];
  if (defaultPort !== undefined) {
    form.port = defaultPort;
  }

  const defaultIp = PROTOCOL_DEFAULT_CLIENT_IP[newType];
  if (defaultIp !== undefined) {
    const protocol = protocols.find((item) => item.value === newType);
    if (!protocol || !protocol.conn_types.includes(form.conn_type)) {
      form.conn_type = 1;
      form.ip = defaultIp;
    }
  } else if (form.conn_type === 1) {
    form.ip = "0.0.0.0";
  }
}

/** Apply the endpoint default only after a user connection-mode change. */
export function applyConnectionTypeDefaults(
  form: ChannelCreateRequest,
  newConnType: number,
  hydrating = false,
): void {
  if (hydrating) return;

  if (newConnType === 1) {
    form.ip = PROTOCOL_DEFAULT_CLIENT_IP[form.protocol_type] ?? "127.0.0.1";
  } else if (newConnType === 2) {
    form.ip = "0.0.0.0";
  }
}
