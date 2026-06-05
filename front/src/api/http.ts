/**
 * HTTP 请求基础设施
 * 集中管理 axios 实例、拦截器、通用请求方法
 */

import axios from 'axios';
import { ElMessage } from 'element-plus';
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

function showErrorOnce(message: string) {
  const now = Date.now();
  if (message === lastErrorMessage && now - lastErrorTime < ERROR_DEBOUNCE_MS) {
    return;
  }
  lastErrorMessage = message;
  lastErrorTime = now;
  ElMessage.error(message);
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
    let message = '网络请求失败';
    if (axios.isAxiosError(error)) {
      message = error.response?.data?.message || error.message;
    } else if (error instanceof Error) {
      message = error.message;
    }
    showErrorOnce(message);
    return Promise.reject(error);
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
