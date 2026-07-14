import {
  HTTP_TIMEOUT,
  HTTP_TIMEOUT_IEC61850_DATASET_READ,
  HTTP_TIMEOUT_LONG,
  HTTP_TIMEOUT_MODEL_DISCOVERY,
} from "@/constants";

// describe('getDeviceList', () => {
//     it('getDeviceList', async () => {
//         const deviceList = await getDeviceList();
//         console.log(deviceList);
//     });
// });

describe("device API timeout policy", () => {
  it("keeps long-running model discovery isolated from normal API timeouts", () => {
    expect(HTTP_TIMEOUT).toBe(5000);
    expect(HTTP_TIMEOUT_IEC61850_DATASET_READ).toBe(10000);
    expect(HTTP_TIMEOUT_LONG).toBe(60000);
    expect(HTTP_TIMEOUT_MODEL_DISCOVERY).toBeGreaterThan(HTTP_TIMEOUT_LONG);
  });
});

// describe('getDeviceInfo', () => {
//     it('getDeviceInfo', async () => {
//         const deviceInfo = await getDeviceInfo("BMS1");
//         console.log(deviceInfo);
//     });
// });
