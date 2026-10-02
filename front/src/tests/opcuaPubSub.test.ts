import {
  csvText,
  decodeUaDrag,
  encodeUaDrag,
  nodeKey,
  rejectionReason,
  uniqueSelections,
  type UaSelection,
} from "@/utils/opcuaPubSub";
const variable: UaSelection = {
  node_id: "ns=2;s=power",
  browse_name: "Power",
  node_class: "Variable",
  history_read: true,
};
describe("OPC UA workspace node transfers", () => {
  it("isolates devices and validates untrusted drag data", () => {
    expect(decodeUaDrag(encodeUaDrag(3, [variable]), 3)[0].node_id).toBe(
      variable.node_id,
    );
    expect(() => decodeUaDrag(encodeUaDrag(3, [variable]), 4)).toThrow(
      "crossChannelDrag",
    );
    expect(() =>
      decodeUaDrag(
        JSON.stringify({ channelId: 3, nodes: [{ node_id: 5 }] }),
        3,
      ),
    ).toThrow("invalidDrag");
    expect(() => decodeUaDrag("x".repeat(1024 * 1024 + 1), 3)).toThrow(
      "invalidDrag",
    );
  });
  it("deduplicates standard NodeId aliases while retaining configured rows", () => {
    const server = {
      node_id: "i=2253",
      browse_name: "Server",
      node_class: "Object",
    };
    expect(nodeKey(" ns=0;i=2253 ")).toBe("i=2253");
    expect(
      uniqueSelections(
        [server],
        [{ ...server, node_id: "ns=0;i=2253", browse_name: "Other" }],
      ),
    ).toEqual([server]);
  });
  it("checks real capabilities rather than node names", () => {
    expect(rejectionReason(variable, "realtime", "client")).toBeNull();
    expect(
      rejectionReason(
        { ...variable, history_read: false },
        "history",
        "client",
      ),
    ).toBe("requireHistory");
    expect(
      rejectionReason(
        { ...variable, history_read: false },
        "history",
        "server",
      ),
    ).toBeNull();
    expect(
      rejectionReason(
        { ...variable, node_class: "Object" },
        "realtime",
        "client",
      ),
    ).toBe("requireVariable");
    const object = {
      node_id: "i=2253",
      browse_name: "Server",
      node_class: "Object",
      event_notifier: true,
    };
    expect(rejectionReason(object, "events", "client")).toBeNull();
    expect(
      rejectionReason({ ...object, event_notifier: false }, "events", "client"),
    ).toBe("requireEventSource");
    expect(rejectionReason(variable, "events", "server")).toBe(
      "requireEventSource",
    );
  });
  it("exports multiline values and neutralizes spreadsheet formulas", () => {
    const csv = csvText(
      ["NodeId", "Value"],
      [
        ["ns=2;s=x", '=HYPERLINK("bad")'],
        ["n", "line1\nline2"],
        ["n", -12],
      ],
    );
    expect(csv).toContain('"\'=HYPERLINK(""bad"")"');
    expect(csv).toContain('"line1\nline2"');
    expect(csv).toContain('"-12"');
  });
});
