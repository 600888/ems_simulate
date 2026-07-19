import type { Component } from "vue";
import {
  Coin,
  Collection,
  Document,
  FolderOpened,
  Grid,
  Memo,
  Promotion,
  SetUp,
  Setting,
} from "@element-plus/icons-vue";

interface Iec61850IconNode {
  isGroup?: boolean;
  iec61850Level?: "category" | "ld" | "ln";
  type?: string;
}

const CATEGORY_ICONS: Record<string, Component> = {
  GOOSE: Promotion,
  Reports: Memo,
  SettingGroups: Setting,
  Files: FolderOpened,
  DataSets: Collection,
  DataModel: Grid,
};

/**
 * Return a semantic icon for IEC 61850 categories and hierarchy nodes.
 * Category icons are intentionally unique so sibling services are easy to scan.
 */
export function getIec61850NodeIcon(node: Iec61850IconNode): Component {
  if (node.iec61850Level === "category") {
    return CATEGORY_ICONS[node.type || ""] || Document;
  }

  if (node.iec61850Level === "ld") {
    return FolderOpened;
  }

  if (node.iec61850Level === "ln") {
    return node.type === "DataSets" && !node.isGroup ? Coin : SetUp;
  }

  return node.isGroup ? FolderOpened : Document;
}
