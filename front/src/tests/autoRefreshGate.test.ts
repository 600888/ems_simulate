import {
  acquireAutoRefreshPause,
  isAutoRefreshPaused,
} from "@/composables/autoRefreshGate";

describe("auto refresh gate", () => {
  it("keeps polling paused until all overlapping operations release", () => {
    const releaseFirst = acquireAutoRefreshPause("first");
    const releaseSecond = acquireAutoRefreshPause("second");

    expect(isAutoRefreshPaused.value).toBe(true);
    releaseFirst();
    expect(isAutoRefreshPaused.value).toBe(true);
    releaseSecond();
    expect(isAutoRefreshPaused.value).toBe(false);

    // Releases are deliberately idempotent for finally/unmount cleanup paths.
    releaseSecond();
    expect(isAutoRefreshPaused.value).toBe(false);
  });
});
