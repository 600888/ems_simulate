import { flattenGooseBlocks } from "@/components/goose/gooseWorkbench";
import type {
  GoosePublisherStatus,
  GooseReceiverStatus,
  GooseSubscriptionStatus,
} from "@/api/gooseApi";

const goCbRef = "TEMPLATEPIGO/LLN0$GO$gocb1";

test("preserves publisher DataModel descriptions in the GOOSE table", () => {
  const publisher = {
    id: "publisher",
    go_cb_ref: goCbRef,
    entries: [
      {
        name: "LD0/GGIO1.Ind1.stVal",
        value: true,
        iec_type: "boolean",
        fc: "ST",
        description: "开关位置",
      },
    ],
  } as unknown as GoosePublisherStatus;
  expect(flattenGooseBlocks([publisher], [])[0].data_values[0]).toMatchObject({
    name: "LD0/GGIO1.Ind1.stVal",
    fc: "ST",
    description: "开关位置",
    value: true,
  });
});

test.each(["TripSignal", "TEMPLATERPIT/LLN0.gocb1", "", goCbRef])(
  "preserves publisher and subscriber GoID independently of GoCBRef: %p",
  (goId) => {
    const publisher = {
      id: "publisher",
      go_cb_ref: goCbRef,
      go_id: goId,
      entries: [],
    } as unknown as GoosePublisherStatus;
    const subscription = {
      go_cb_ref: goCbRef,
      go_id: goId,
      data_values: [],
    } as unknown as GooseSubscriptionStatus;
    const receiver = {
      id: "receiver",
      subscriptions: [subscription],
    } as unknown as GooseReceiverStatus;

    const blocks = flattenGooseBlocks([publisher], [receiver]);

    expect(blocks).toHaveLength(2);
    for (const block of blocks) {
      expect(block.go_cb_ref).toBe(goCbRef);
      expect(block.go_id).toBe(goId);
    }
  },
);
