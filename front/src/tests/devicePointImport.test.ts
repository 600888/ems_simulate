import { importDevicePointFile } from "@/utils/devicePointImport";
import { importPoints } from "@/api/channelApi";

jest.mock("@/api/channelApi", () => ({ importPoints: jest.fn() }));
const legacyImport = importPoints as jest.MockedFunction<typeof importPoints>;

describe("device form point import routing", () => {
  const file = new File(["workbook"], "point_sample_opcua.xlsx");
  beforeEach(() => legacyImport.mockReset());

  it("uses the OPC UA review flow for both new and edited channels", async () => {
    const review = jest.fn().mockResolvedValue(true);
    await expect(importDevicePointFile(7, 21, file, review)).resolves.toBe(
      true,
    );
    expect(review).toHaveBeenCalledWith(21, file);
    expect(legacyImport).not.toHaveBeenCalled();
  });

  it("does not fall back to the numeric importer when OPC UA review is cancelled", async () => {
    const review = jest.fn().mockResolvedValue(false);
    await expect(importDevicePointFile(7, 21, file, review)).resolves.toBe(
      false,
    );
    expect(legacyImport).not.toHaveBeenCalled();
  });

  it("does not fall back when OPC UA review fails", async () => {
    const review = jest
      .fn()
      .mockRejectedValue(new Error("preview unavailable"));
    await expect(importDevicePointFile(7, 21, file, review)).rejects.toThrow(
      "preview unavailable",
    );
    expect(legacyImport).not.toHaveBeenCalled();
  });

  it("preserves legacy point import for other protocols", async () => {
    const review = jest.fn();
    await expect(importDevicePointFile(2, 21, file, review)).resolves.toBe(
      true,
    );
    expect(legacyImport).toHaveBeenCalledWith(21, file);
    expect(review).not.toHaveBeenCalled();
  });
});
