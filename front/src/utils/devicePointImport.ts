import { importPoints } from "@/api/channelApi";
import { PROTOCOL_TYPE } from "@/constants/protocol";

/** OPC UA needs its own preview/confirmation; legacy protocols use numeric point tables. */
export async function importDevicePointFile(
  protocolType: number,
  channelId: number,
  file: File,
  reviewOpcUa: (channelId: number, file: File) => Promise<boolean>,
): Promise<boolean> {
  if (protocolType === PROTOCOL_TYPE.OPCUA) return reviewOpcUa(channelId, file);
  await importPoints(channelId, file);
  return true;
}
