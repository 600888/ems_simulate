import type { TreeNode } from "@/composables";

type TranslateFn = (key: string, params?: Record<string, unknown>) => string;

export function buildDlt645Children(
  deviceName: string,
  keyPrefix = "device",
  t?: TranslateFn,
): TreeNode[] {
  const translate = (key: string, params?: Record<string, unknown>) =>
    t ? t(key, params) : key;
  const settlementLabels = [
    translate("sidebar.dlt645.current"),
    ...Array.from({ length: 12 }, (_, index) =>
      translate("sidebar.dlt645.prevSettlement", { n: index + 1 }),
    ),
  ];
  const categories = [
    { prefix: 0, label: translate("sidebar.dlt645.energy"), settlements: true },
    {
      prefix: 1,
      label: translate("sidebar.dlt645.maxDemand"),
      settlements: true,
    },
    { prefix: 2, label: translate("sidebar.dlt645.variables") },
    { prefix: 3, label: translate("sidebar.dlt645.events") },
    { prefix: 4, label: translate("sidebar.dlt645.paramVars") },
  ];
  return categories.map((category) => {
    const children = category.settlements
      ? settlementLabels.map((label, settlement) => ({
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
