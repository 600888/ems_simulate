import type {
  GoosePublisherStatus,
  GooseReceiverStatus,
  GooseSubscriptionDataValue,
  GooseSubscriptionStatus,
} from '@/api/gooseApi';

export type GooseBlockKind = 'publisher' | 'subscriber';

export interface GooseBlockItem {
  key: string;
  kind: GooseBlockKind;
  display_name: string;
  ied_name: string;
  ld_inst: string;
  ln_name: string;
  go_cb_ref: string;
  go_id: string;
  data_set_ref: string;
  app_id: number | null;
  conf_rev: number;
  st_num: number;
  sq_num: number;
  enabled: boolean;
  state: 'init' | 'connected' | 'lost' | 'error';
  interface: string;
  dst_mac: string;
  last_update: number;
  message_count: number;
  data_values: GooseSubscriptionDataValue[];
  publisher?: GoosePublisherStatus;
  subscription?: GooseSubscriptionStatus;
  receiver_id?: string;
}

export function flattenGooseBlocks(
  publishers: GoosePublisherStatus[],
  receivers: GooseReceiverStatus[],
): GooseBlockItem[] {
  const publisherBlocks = publishers.map((publisher): GooseBlockItem => {
    const parsed = parseGoCbRef(publisher.go_cb_ref, 'Local IED');
    return {
      key: `publisher::${publisher.id}`,
      kind: 'publisher',
      display_name: parsed.name,
      ied_name: parsed.ied,
      ld_inst: parsed.ld,
      ln_name: parsed.ln,
      go_cb_ref: publisher.go_cb_ref,
      go_id: publisher.go_cb_ref || publisher.go_id,
      data_set_ref: publisher.data_set_ref,
      app_id: publisher.app_id,
      conf_rev: publisher.conf_rev,
      st_num: publisher.st_num,
      sq_num: publisher.sq_num,
      enabled: publisher.is_running,
      state: publisher.is_running ? 'connected' : 'init',
      interface: publisher.interface,
      dst_mac: publisher.dst_mac || '',
      last_update: 0,
      message_count: publisher.sq_num || 0,
      data_values: (publisher.entries || []).map((entry, index) => ({
        index: entry.index ?? index,
        name: entry.name,
        type: entry.iec_type,
        value: entry.value,
      })),
      publisher,
    };
  });

  const subscriberBlocks = receivers.flatMap((receiver) =>
    (receiver.subscriptions || []).map((subscription): GooseBlockItem => {
      const parsed = parseGoCbRef(subscription.go_cb_ref, subscription.ied_name || 'Remote IED');
      return {
        key: `subscriber::${receiver.id}::${subscription.go_cb_ref}`,
        kind: 'subscriber',
        display_name: parsed.name,
        ied_name: subscription.ied_name || parsed.ied,
        ld_inst: subscription.ld_inst || parsed.ld,
        ln_name: subscription.ln_name || parsed.ln,
        go_cb_ref: subscription.go_cb_ref,
        go_id: subscription.go_cb_ref || subscription.go_id,
        data_set_ref: subscription.data_set_ref,
        app_id: subscription.app_id,
        conf_rev: subscription.conf_rev,
        st_num: subscription.st_num,
        sq_num: subscription.sq_num,
        enabled: subscription.enabled,
        state: subscription.state,
        interface: receiver.interface,
        dst_mac: subscription.dst_mac || '',
        last_update: subscription.last_update,
        message_count: subscription.message_count,
        data_values: subscription.data_values,
        subscription,
        receiver_id: receiver.id,
      };
    }),
  );

  return [...publisherBlocks, ...subscriberBlocks];
}

export function parseGoCbRef(ref: string, fallbackIed = 'Remote IED') {
  const [pathPart = '', controlName = 'GOOSE'] = ref.split('$GO$');
  const [ldPart = '', lnPart = 'LLN0'] = pathPart.split('/');
  return { ied: fallbackIed, ld: ldPart || 'LD0', ln: lnPart || 'LLN0', name: controlName || ref };
}

export function formatGooseTime(value: number): string {
  if (!value) return '-';
  return new Date(value * 1000).toLocaleString();
}
