/**
 * GOOSE 抓包 WebSocket 管理器
 *
 * 设计模式:
 * - 单例模式 (Singleton): 全局唯一 WebSocket 连接
 * - 观察者模式 (Observer): 组件订阅消息事件，解耦发送方与接收方
 * - 命令模式 (Command): 通过统一的消息协议封装操作指令
 *
 * 消息协议:
 *   Client → Server: { type: "command", action: "start|stop|clear|list|status", params?: {...} }
 *   Server → Client: { type: "packet", data: {...} }
 *                     { type: "response", command: "...", success: true, data: {...} }
 *                     { type: "error", message: "..." }
 *                     { type: "statistics", data: {...} }
 *
 * 用法:
 *   const ws = GooseCaptureWebSocket.getInstance();
 *   const unsub = ws.on('packet', (pkt) => { ... });
 *   ws.start({ interface: 'eth0' });
 *   ws.on('disconnected', () => { ... });
 *   // 组件销毁时:
 *   unsub();
 */

import { WS_RECONNECT_INTERVAL } from '@/constants/app';

// ===== 类型定义 =====

/** WebSocket 事件类型 */
export enum WsEventType {
  /** 收到实时 GOOSE 报文 */
  PACKET = 'packet',
  /** 收到指令响应 */
  RESPONSE = 'response',
  /** 收到统计数据更新 */
  STATISTICS = 'statistics',
  /** 收到错误消息 */
  ERROR = 'error',
  /** WebSocket 连接已建立 */
  CONNECTED = 'connected',
  /** WebSocket 连接已断开 */
  DISCONNECTED = 'disconnected',
}

/** 消息类型常量 (与服务端对齐) */
const MSG_COMMAND = 'command';
const MSG_RESPONSE = 'response';
const MSG_ERROR = 'error';
const MSG_STATISTICS = 'statistics';

/** WebSocket 事件处理器 */
type WsEventHandler = (data: any) => void;

/** 连接状态 */
export enum ConnectionState {
  DISCONNECTED = 'disconnected',
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  RECONNECTING = 'reconnecting',
}

// ===== WebSocket 管理器 (单例) =====

export class GooseCaptureWebSocket {
  // ---- 单例 ----
  private static _instance: GooseCaptureWebSocket | null = null;
  public static getInstance(): GooseCaptureWebSocket {
    if (!GooseCaptureWebSocket._instance) {
      GooseCaptureWebSocket._instance = new GooseCaptureWebSocket();
    }
    return GooseCaptureWebSocket._instance;
  }

  // ---- 私有属性 ----
  private _ws: WebSocket | null = null;
  private _connectionState: ConnectionState = ConnectionState.DISCONNECTED;
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private _reconnectAttempts = 0;
  private _maxReconnectAttempts = 10;
  private _destroyed = false;

  /** 观察者注册表: 事件名 → 处理器列表 */
  private _listeners: Map<string, Set<WsEventHandler>> = new Map();

  /** 待发送的命令队列 (连接建立前缓存) */
  private _pendingCommands: Array<{ action: string; params?: any }> = [];

  /** 获取 baseURL */
  private get _baseUrl(): string {
    // 从 axios 实例获取 baseURL
    const axios = (window as any).__axios_instance;
    let baseURL = '/';
    if (axios?.defaults?.baseURL) {
      baseURL = axios.defaults.baseURL;
    }
    if (baseURL.startsWith('/')) {
      baseURL = window.location.origin + baseURL;
    }
    return baseURL;
  }

  /** 获取 WebSocket URL */
  private get _wsUrl(): string {
    const base = this._baseUrl;
    const wsBase = base.replace(/^http/, 'ws');
    return `${wsBase.replace(/\/$/, '')}/api/channels/goose/capture/ws`;
  }

  // ===== 公开 API =====

  /** 获取当前连接状态 */
  get connectionState(): ConnectionState {
    return this._connectionState;
  }

  /** 是否已连接 */
  get isConnected(): boolean {
    return this._connectionState === ConnectionState.CONNECTED;
  }

  /**
   * 订阅 WebSocket 事件
   * @returns 取消订阅函数
   */
  on(event: WsEventType, handler: WsEventHandler): () => void {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, new Set());
    }
    this._listeners.get(event)!.add(handler);

    // 返回取消订阅函数
    return () => {
      this._listeners.get(event)?.delete(handler);
    };
  }

  /**
   * 一次性订阅
   */
  once(event: WsEventType, handler: WsEventHandler): () => void {
    const wrapper = (data: any) => {
      handler(data);
      unsub();
    };
    const unsub = this.on(event, wrapper);
    return unsub;
  }

  /**
   * 建立 WebSocket 连接
   */
  connect(): void {
    if (this._destroyed) return;
    if (
      this._connectionState === ConnectionState.CONNECTED ||
      this._connectionState === ConnectionState.CONNECTING
    ) {
      return;
    }

    this._connectionState = ConnectionState.CONNECTING;
    this._emit(WsEventType.CONNECTED, { state: ConnectionState.CONNECTING });

    try {
      this._ws = new WebSocket(this._wsUrl);

      this._ws.onopen = () => {
        this._connectionState = ConnectionState.CONNECTED;
        this._reconnectAttempts = 0;
        this._emit(WsEventType.CONNECTED, { state: ConnectionState.CONNECTED });

        // 发送积压的命令
        while (this._pendingCommands.length > 0) {
          const cmd = this._pendingCommands.shift()!;
          this._sendCommand(cmd.action, cmd.params);
        }
      };

      this._ws.onmessage = (event: MessageEvent) => {
        try {
          const message = JSON.parse(event.data);
          this._dispatch(message);
        } catch (e) {
          console.error('[GooseCaptureWS] 解析消息失败:', e);
        }
      };

      this._ws.onclose = () => {
        this._connectionState = ConnectionState.DISCONNECTED;
        this._emit(WsEventType.DISCONNECTED, { state: ConnectionState.DISCONNECTED });
        this._ws = null;
        this._scheduleReconnect();
      };

      this._ws.onerror = (err: Event) => {
        console.error('[GooseCaptureWS] 连接错误:', err);
        this._ws?.close();
      };
    } catch (e) {
      console.error('[GooseCaptureWS] 创建连接失败:', e);
      this._connectionState = ConnectionState.DISCONNECTED;
      this._scheduleReconnect();
    }
  }

  /**
   * 断开 WebSocket 连接
   */
  disconnect(): void {
    this._destroyed = true;
    this._clearReconnectTimer();

    if (this._ws) {
      this._ws.onclose = null; // 阻止触发重连
      this._ws.close();
      this._ws = null;
    }

    this._connectionState = ConnectionState.DISCONNECTED;
    this._emit(WsEventType.DISCONNECTED, { state: ConnectionState.DISCONNECTED });
    this._listeners.clear();
    this._pendingCommands = [];
    GooseCaptureWebSocket._instance = null;
  }

  // ===== 指令封装 (Command Pattern) =====

  /** 启动 GOOSE 抓包 */
  start(params: { channel_id: number; interface?: string; max_packets?: number; filter_app_id?: number | null }): void {
    this._sendCommand('start', params);
  }

  /** 停止 GOOSE 抓包 */
  stop(channelId: number): void {
    this._sendCommand('stop', { channel_id: channelId });
  }

  /** 清空报文 */
  clear(channelId: number): void {
    this._sendCommand('clear', { channel_id: channelId });
  }

  /** 获取报文列表 */
  list(params: { channel_id: number; count?: number; filter_app_id?: number | null }): void {
    this._sendCommand('list', params);
  }

  /** 获取状态 */
  status(channelId: number): void {
    this._sendCommand('status', { channel_id: channelId });
  }

  // ===== 内部方法 =====

  /** 发送指令 (Command Pattern) */
  private _sendCommand(action: string, params?: any): void {
    const message = { type: MSG_COMMAND, action, params };
    const payload = JSON.stringify(message);

    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(payload);
    } else {
      // 连接未就绪，缓存命令
      this._pendingCommands.push({ action, params });
      // 如果还没连接，自动发起连接
      if (
        this._connectionState === ConnectionState.DISCONNECTED &&
        !this._destroyed
      ) {
        this.connect();
      }
    }
  }

  /** 分发服务端消息 (Observer Pattern) */
  private _dispatch(message: any): void {
    const msgType = message.type;

    switch (msgType) {
      case 'packet':
        this._emit(WsEventType.PACKET, message.data);
        break;
      case MSG_RESPONSE:
        this._emit(WsEventType.RESPONSE, {
          command: message.command,
          success: message.success,
          data: message.data,
          message: message.message,
        });
        break;
      case MSG_STATISTICS:
        this._emit(WsEventType.STATISTICS, message.data);
        break;
      case MSG_ERROR:
        this._emit(WsEventType.ERROR, { message: message.message });
        break;
      default:
        console.warn('[GooseCaptureWS] 未知消息类型:', msgType);
    }
  }

  /** 触发事件，通知所有订阅者 */
  private _emit(event: WsEventType, data: any): void {
    const handlers = this._listeners.get(event);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(data);
        } catch (e) {
          console.error(`[GooseCaptureWS] 事件处理器异常 (${event}):`, e);
        }
      });
    }
  }

  /** 安排自动重连 */
  private _scheduleReconnect(): void {
    if (this._destroyed) return;
    if (this._reconnectAttempts >= this._maxReconnectAttempts) {
      console.warn('[GooseCaptureWS] 重连次数已达上限，停止重连');
      return;
    }

    this._clearReconnectTimer();
    this._connectionState = ConnectionState.RECONNECTING;
    this._emit(WsEventType.DISCONNECTED, { state: ConnectionState.RECONNECTING });

    // 指数退避: 3s, 3s, 6s, 12s, ... (最多 30s)
    const delay = Math.min(
      WS_RECONNECT_INTERVAL * Math.pow(2, this._reconnectAttempts),
      30000,
    );
    this._reconnectAttempts++;

    console.log(`[GooseCaptureWS] ${delay}ms 后尝试第 ${this._reconnectAttempts} 次重连`);
    this._reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  private _clearReconnectTimer(): void {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }
}

/**
 * 便捷函数: 获取单例
 */
export function useGooseCaptureWS(): GooseCaptureWebSocket {
  return GooseCaptureWebSocket.getInstance();
}
