import {
  csvText,
  decodeUaDrag,
  encodeUaDrag,
  nodeKey,
  rejectionReason,
  uniqueSelections,
  mergeDiscoveredMonitors,
  defaultMonitor,
  type UaSelection,
} from "@/utils/opcuaPubSub";
const variable: UaSelection = {
  node_id: "ns=2;s=power",
  browse_name: "Power",
  node_class: "Variable",
  history_read: true,
};
describe("OPC UA workspace node transfers", () => {
  it("merges discovery without changing existing sampling settings or duplicating namespace identities", () => {
    const existing = {
      ...defaultMonitor("ns=2;s=power"),
      namespace_uri: "urn:plant",
      sampling_interval_ms: 1200,
    };
    const discovered = {
      ...variable,
      namespace_uri: "urn:plant",
      namespace_index: 4,
      readable: true,
      writable: false,
      value_rank: -1,
      data_type: "Double",
    };
    const next = { ...discovered, node_id: "ns=4;s=next" };
    const merged = mergeDiscoveredMonitors(
      [existing],
      [{ ...discovered, node_id: "ns=4;s=power" }, next, next],
    );
    expect(merged.items).toHaveLength(2);
    expect(merged.items[0]).toBe(existing);
    expect(merged.items[0].sampling_interval_ms).toBe(1200);
    expect(merged.items[1].namespace_uri).toBe("urn:plant");
    expect(merged.added).toEqual([next]);
    expect(
      mergeDiscoveredMonitors([defaultMonitor(variable.node_id)], [discovered])
        .added,
    ).toEqual([]);
    expect(mergeDiscoveredMonitors([existing], [next], 1).overflow).toBe(true);
    expect(
      mergeDiscoveredMonitors([], [{ ...next, readable: false }]).items,
    ).toEqual([]);
  });
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
