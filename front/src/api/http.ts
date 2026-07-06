/**
 * HTTP 请求基础设施
 * 集中管理 axios 实例、拦截器、通用请求方法
 */

import axios from 'axios';
import { ElMessage } from 'element-plus';
import 'element-plus/es/components/message/style/css';
import { HTTP_TIMEOUT, ERROR_DEBOUNCE_MS } from '@/constants';

const API_BASE_URL = import.meta.env.VUE_APP_API_BASE || '/';

export const instance = axios.create({
  baseURL: API_BASE_URL,
  timeout: HTTP_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 错误消息去重：避免后端阻塞时多个请求同时超时导致不停弹窗
let lastErrorMessage = '';
let lastErrorTime = 0;
// 最多同时显示 3 条错误消息
const MAX_ERROR_COUNT = 3;
const activeErrorMessages: { close: () => void }[] = [];

function showErrorOnce(message: string) {
  const now = Date.now();
  if (message === lastErrorMessage && now - lastErrorTime < ERROR_DEBOUNCE_MS) {
    return;
  }
  lastErrorMessage = message;
  lastErrorTime = now;
  // 超过上限时关闭最早的一条
  if (activeErrorMessages.length >= MAX_ERROR_COUNT) {
    const oldest = activeErrorMessages.shift();
    oldest?.close();
  }
  const msg = ElMessage.error(message);
  activeErrorMessages.push(msg);
  // 消息关闭时从数组中移除
  const origClose = msg.close.bind(msg);
  msg.close = () => {
    const idx = activeErrorMessages.indexOf(msg);
    if (idx !== -1) activeErrorMessages.splice(idx, 1);
    origClose();
  };
}

export function getApiErrorMessage(error: unknown, fallback = '请求失败'): string {
  if (axios.isAxiosError(error)) {
    const respData = error.response?.data;

    if (respData) {
      if (typeof respData === 'object') {
        const responseMessage = (respData as { message?: unknown; detail?: unknown }).message
          ?? (respData as { message?: unknown; detail?: unknown }).detail;
        if (typeof responseMessage === 'string' && responseMessage.trim()) {
          return responseMessage;
        }
      }

      if (typeof respData === 'string' && respData.trim()) {
        try {
          const parsed = JSON.parse(respData);
          if (typeof parsed?.message === 'string' && parsed.message.trim()) {
            return parsed.message;
          }
          if (typeof parsed?.detail === 'string' && parsed.detail.trim()) {
            return parsed.detail;
          }
        } catch {
          return respData;
        }
      }
    }

    if (error.response?.status) {
      return `${fallback} (${error.response.status})`;
    }
    if (error.message) {
      return `网络请求失败: ${error.message}`;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}
// 响应拦截器
instance.interceptors.response.use(
  (response) => {
    // 仅对 JSON 对象响应检查业务状态码（非 JSON 如原始 XML/文本直接放行）
    if (typeof response.data === 'object' && response.data && response.data.code !== 200) {
      const errorMsg = response.data.message || '请求失败';
      showErrorOnce(errorMsg);
      return Promise.reject(new Error(errorMsg));
    }
    return response;
  },
  (error) => {
    const message = getApiErrorMessage(error, '网络请求失败');
    showErrorOnce(message);
    return Promise.reject(new Error(message));
  },
);

/**
 * 通用请求方法
 * @param url 请求路径
 * @param method 请求方法
 * @param data 请求数据
 * @param timeout 可选超时时间（毫秒），覆盖默认值
 * @returns 响应 data 字段
 */
export const requestApi = async (url: string, method: string, data: any, timeout?: number): Promise<any> => {
  const response = await instance.request({ url, method, data, timeout });
  return response.data.data;
};
