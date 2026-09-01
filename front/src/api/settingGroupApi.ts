import { requestApi } from "./http";
import { SETTING_GROUP_API } from "@/constants/api";

export interface SettingGroupControl {
  name: string;
  ref: string;
  ld: string;
  ln: string;
}

export interface SettingValue {
  address: string;
  ref: string;
  code: string;
  description: string;
  unit: string;
  iec_type: string;
  mms_type: string;
  current_value: unknown;
  edit_value: unknown;
}

export interface SettingGroupDetail extends SettingGroupControl {
  num_of_sg: number | null;
  act_sg: number | null;
  edit_sg: number | null;
  cnf_edit: boolean | null;
  last_activation_time: number | string | null;
  reservation_time: number | null;
  writable: boolean;
  settings: SettingValue[];
}

export async function listSettingGroups(
  channelId: number,
): Promise<SettingGroupControl[]> {
  const result = await requestApi(SETTING_GROUP_API.LIST, "post", {
    channel_id: channelId,
  });
  return result?.items || [];
}

export async function getSettingGroupDetail(
  channelId: number,
  sgcbRef: string,
): Promise<SettingGroupDetail | null> {
  return await requestApi(SETTING_GROUP_API.DETAIL, "post", {
    channel_id: channelId,
    sgcb_ref: sgcbRef,
  });
}

export async function selectEditGroup(
  channelId: number,
  sgcbRef: string,
  group: number,
): Promise<boolean> {
  const result = await requestApi(SETTING_GROUP_API.SELECT_EDIT, "post", {
    channel_id: channelId,
    sgcb_ref: sgcbRef,
    group,
  });
  return result?.success === true;
}

export async function writeSettingValues(
  channelId: number,
  sgcbRef: string,
  values: { address: string; value: unknown }[],
): Promise<boolean> {
  const result = await requestApi(SETTING_GROUP_API.WRITE, "post", {
    channel_id: channelId,
    sgcb_ref: sgcbRef,
    values,
  });
  return result?.success === true;
}

export async function confirmSettingGroup(
  channelId: number,
  sgcbRef: string,
): Promise<boolean> {
  const result = await requestApi(SETTING_GROUP_API.CONFIRM, "post", {
    channel_id: channelId,
    sgcb_ref: sgcbRef,
  });
  return result?.success === true;
}

export async function activateSettingGroup(
  channelId: number,
  sgcbRef: string,
  group: number,
): Promise<boolean> {
  const result = await requestApi(SETTING_GROUP_API.ACTIVATE, "post", {
    channel_id: channelId,
    sgcb_ref: sgcbRef,
    group,
  });
  return result?.success === true;
}
