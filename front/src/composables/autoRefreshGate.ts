import { ref } from "vue";

export const isAutoRefreshPaused = ref(false);

const pauseTokens = new Set<symbol>();

/** Pause polling until the returned idempotent release function is called. */
export function acquireAutoRefreshPause(reason = "long-running-operation"): () => void {
  const token = Symbol(reason);
  pauseTokens.add(token);
  isAutoRefreshPaused.value = true;

  let released = false;
  return () => {
    if (released) return;
    released = true;
    pauseTokens.delete(token);
    isAutoRefreshPaused.value = pauseTokens.size > 0;
  };
}
