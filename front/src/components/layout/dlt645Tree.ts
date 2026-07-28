import type { TreeNode } from "@/composables";

const SETTLEMENT_LABELS = [
  "当前",
  ...Array.from({ length: 12 }, (_, index) => `上 ${index + 1} 结算日`),
];

const CATEGORIES = [
  { prefix: 0, label: "电能量", settlements: true },
  { prefix: 1, label: "最大需量及发生时间", settlements: true },
  { prefix: 2, label: "变量" },
  { prefix: 3, label: "事件记录" },
  { prefix: 4, label: "参变量" },
];

export function buildDlt645Children(
  deviceName: string,
  keyPrefix = "device",
): TreeNode[] {
  return CATEGORIES.map((category) => {
    const children = category.settlements
      ? SETTLEMENT_LABELS.map((label, settlement) => ({
          nodeKey: `${keyPrefix}-${deviceName}-dlt645-${category.prefix}-${settlement}`,
          label,
          isGroup: false,
          id: 0,
          name: label,
          deviceName,
          isDlt645Child: true,
          dlt645Prefix: category.prefix,
          dlt645Settlement: settlement,
        }))
      : undefined;

    return {
      nodeKey: `${keyPrefix}-${deviceName}-dlt645-${category.prefix}`,
      label: category.label,
      isGroup: Boolean(children),
      id: 0,
      name: category.label,
      deviceName,
      children,
      isDlt645Child: true,
      dlt645Prefix: category.prefix,
    };
  });
}
