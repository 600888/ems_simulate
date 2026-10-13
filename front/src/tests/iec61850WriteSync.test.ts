import type { IEC61850DoNode } from "@/api/channelApi";
import {
  resolveIec61850ReadbackTarget,
  syncIec61850WriteResult,
} from "@/utils/iec61850WriteSync";

const target = { pointCode: "status-code", fc: "ST", mmsType: "MMS_BOOLEAN" };

describe("IEC61850 write feedback", () => {
  it("replaces a previous read of zero with feedback after a successful command", async () => {
    const cache = new Map<string, unknown>([[target.pointCode, 0]]);
    const read = jest.fn().mockResolvedValue({ value: 1 });

    await syncIec61850WriteResult(
      { point_code: "control-code", value: 1 },
      target,
      read,
      (code, value) => cache.set(code, value),
    );

    expect(read).toHaveBeenCalledWith(target);
    expect(cache.get(target.pointCode)).toBe(1);
    expect(cache.get("control-code")).toBe(1);
  });

  it("shows actual zero feedback even when the accepted command was one", async () => {
    const cache = new Map<string, unknown>();
    await syncIec61850WriteResult(
      { point_code: "control-code", value: 1 },
      target,
      async () => ({ value: 0 }),
      (code, value) => cache.set(code, value),
    );

    expect(cache.get("control-code")).toBe(1);
    expect(cache.get(target.pointCode)).toBe(0);
  });

  it("reads the requested status code even if writing redirects to Oper.ctlVal", async () => {
    const update = jest.fn();
    await syncIec61850WriteResult(
      { point_code: "control-code", value: 0 },
      target,
      async () => ({ value: false }),
      update,
    );

    expect(update).toHaveBeenLastCalledWith("status-code", false);
  });

  it("does not attempt an MMS read for a command with no feedback attribute", async () => {
    const read = jest.fn();
    await syncIec61850WriteResult(
      { point_code: "control-code", value: 1 },
      null,
      read,
      jest.fn(),
    );
    expect(read).not.toHaveBeenCalled();
  });

  it("preserves the accepted command if reading feedback fails", async () => {
    const update = jest.fn();
    await expect(
      syncIec61850WriteResult(
        { point_code: "control-code", value: 1 },
        target,
        async () => {
          throw new Error("read failed");
        },
        update,
      ),
    ).rejects.toThrow("read failed");
    expect(update).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledWith("control-code", 1);
  });
});

describe("control status target", () => {
  it("uses the real registered stVal code instead of the command or its Check field", () => {
    const node = {
      children: [
        {
          da_path: "Oper",
          fc: "CO",
          point_code: "",
          children: [
            { bda_path: "Oper.Check", fc: "CO", point_code: "check-code" },
            { bda_path: "Oper.ctlVal", fc: "CO", point_code: "control-code" },
          ],
        },
        {
          da_path: "stVal",
          fc: "ST",
          point_code: "status-code",
          mms_type: "MMS_BOOLEAN",
        },
      ],
    } as IEC61850DoNode;
    expect(resolveIec61850ReadbackTarget(node)).toEqual(target);
  });

  it("does not invent stVal when a control exposes only CO attributes", () => {
    const node = {
      children: [
        { da_path: "Oper.ctlVal", fc: "CO", point_code: "control-code" },
      ],
    } as IEC61850DoNode;
    expect(resolveIec61850ReadbackTarget(node)).toBeNull();
  });
});
