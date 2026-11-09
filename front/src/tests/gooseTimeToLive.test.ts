import { remainingGooseTimeToLive } from "@/components/goose/gooseWorkbench";
import type { GooseSubscriptionStatus } from "@/api/gooseApi";

const received = {
  enabled: true,
  state: "connected" as const,
  last_update: 1794272400,
  time_allowed_to_live: 5000,
};
const receivedAt = received.last_update * 1000;

test("counts down from local reception and clamps at zero after expiry", () => {
  expect(remainingGooseTimeToLive(received, receivedAt)).toBe(5000);
  expect(remainingGooseTimeToLive(received, receivedAt + 1250)).toBe(3750);
  expect(remainingGooseTimeToLive(received, receivedAt + 5000)).toBe(0);
  expect(remainingGooseTimeToLive(received, receivedAt + 6000)).toBe(0);
});

test("a new frame resets the deadline using its own advertised TAL", () => {
  const now = receivedAt + 6000;
  expect(remainingGooseTimeToLive(received, now)).toBe(0);
  const next = {
    ...received,
    last_update: (now - 100) / 1000,
    time_allowed_to_live: 2000,
  };
  expect(remainingGooseTimeToLive(next, now)).toBe(1900);
});

test.each([
  undefined,
  null,
  { ...received, last_update: 0 },
  { ...received, enabled: false },
  { ...received, state: "init" as const },
  { ...received, time_allowed_to_live: 0 },
  { ...received, last_update: Number.NaN },
  { ...received, time_allowed_to_live: Number.NaN },
])(
  "shows no countdown when supervision is inactive or has no received frame: %p",
  (subscription) => {
    expect(remainingGooseTimeToLive(subscription, receivedAt)).toBeNull();
  },
);

test("clock skew cannot increase the remaining time beyond the frame's TAL", () => {
  expect(remainingGooseTimeToLive(received, receivedAt - 2000)).toBe(5000);
});

test.each<GooseSubscriptionStatus["state"]>(["lost", "error"])(
  "preserves the expiry calculation for a subscription with %s state",
  (state) => {
    expect(
      remainingGooseTimeToLive({ ...received, state }, receivedAt + 6000),
    ).toBe(0);
  },
);
