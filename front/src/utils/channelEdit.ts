export interface SecuritySaveState {
  isEdit: boolean;
  tlsSupported: boolean;
  tlsEnabled: boolean;
  tlsMode: "basic" | "mutual";
  originalTlsEnabled: boolean;
  originalTlsMode: "basic" | "mutual";
  hasNewFiles: boolean;
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
