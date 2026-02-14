import { PointType, type PointLimit } from '@/types/point';
import axios from 'axios';
// const apiUrl = "http://127.0.0.1:8888";
// 使用相对路径，Nginx会代理到正确的后端地址
const API_BASE_URL = import.meta.env.VUE_APP_API_BASE || '/'; // Nginx会将/api代理到实际后端

export const instance = axios.create({
    baseURL: API_BASE_URL,
    timeout: 3000,
    headers: {
        'Content-Type': 'application/json'
    }
});

// 封装请求方法
export const requestApi = async (url: string, method: string, data: any): Promise<any> => {
    try {
        const response = await instance.request({
            url,
            method,
            data
        });
        // 检查业务响应码
        if (response.data.code !== 200) {
            throw new Error(response.data.message || '请求失败');
        }
        return response.data.data;
    } catch (error) {
        // 统一错误处理
        if (axios.isAxiosError(error)) {
            throw new Error(error.response?.data?.message || error.message);
        }
        throw error;
    }
}
export async function getDeviceList(): Promise<Array<string>> {
    try {
        const data = await requestApi(`/device/get_device_list`, 'post', null);
        return data;
    } catch (error) {
        console.error('Error fetching device list:', error);
        throw error;
    }
}

export async function getDeviceInfo(deviceName: string): Promise<Map<string, any>> {
    try {
        const data = await requestApi(`/device/get_device_info`, 'post', { device_name: deviceName });
        // 将返回的对象转换为 Map
        const deviceInfoMap = new Map<string, any>(Object.entries(data));
        return deviceInfoMap;
    } catch (error) {
        console.error('Error fetching device info:', error);
        throw error;
    }
}

export async function startSimulation(deviceName: string, simulateMethod: string): Promise<boolean> {
    try {
        const data = await requestApi(`/device/start_simulation`, 'post',
            {
                device_name: deviceName,
                simulate_method: simulateMethod
            },
        );
        return data;
    } catch (error) {
        console.error('Error start simulation:', error);
        throw error;
    }
}


export async function stopSimulation(deviceName: string): Promise<boolean> {
    try {
        const data = await requestApi(`/device/stop_simulation`, 'post', {
            device_name: deviceName,
        },
        );
        return data;
    } catch (error) {
        console.error('Error stop simulation:', error);
        throw error;
    }
}

export async function startDevice(deviceName: string): Promise<boolean> {
    try {
        const data = await requestApi(`/device/start`, 'post', {
            device_name: deviceName,
        });
        return data;
    } catch (error) {
        console.error('Error starting device:', error);
        throw error;
    }
}

export async function stopDevice(deviceName: string): Promise<boolean> {
    try {
        const data = await requestApi(`/device/stop`, 'post', {
            device_name: deviceName,
        });
        return data;
    } catch (error) {
        console.error('Error stopping device:', error);
        throw error;
    }
}

export async function getSlaveIdList(deviceName: string): Promise<Array<number>> {
    try {
        const data = await requestApi(`/device/get_slave_id_list`, 'post',
            {
                device_name: deviceName,
            },
        );
        return data;
    } catch (error) {
        console.error('Error stop simulation:', error);
        throw error;
    }
}

export async function getDeviceTable(deviceName: string, slaveId: number, pointName: string | null, pageIndex: number,
    pageSize: number, pointTypes: number[]): Promise<Map<string, any>> {
    try {
        const data = await requestApi(`/device/get_device_table`, 'post', {
            device_name: deviceName,
            slave_id: slaveId,
            point_name: pointName,
            page_index: pageIndex,
            page_size: pageSize,
            point_types: pointTypes
        });
        // 将返回的对象转换为 Map
        const deviceInfoMap = new Map<string, any>(Object.entries(data));
        return deviceInfoMap;
    } catch (error) {
        console.error('Error stop simulation:', error);
        throw error;
    }
}

export async function editPointData(deviceName: string, pointCode: string, pointValue: number): Promise<boolean> {
    try {
        const data = await requestApi('/device/edit_point_data/', 'post', {
            device_name: deviceName,
            point_code: pointCode,
            point_value: pointValue,
        });
        return data;
    } catch (error) {
        console.error('Error stop simulation:', error);
        return false;
    }
}


export async function editPointLimit(deviceName: string, pointCode: string, minValueLimit: number, maxValueLimit: number): Promise<boolean> {
    try {
        const data = await requestApi('/device/edit_point_limit/', 'post', {
            device_name: deviceName,
            point_code: pointCode,
            min_value_limit: minValueLimit,
            max_value_limit: maxValueLimit,
        });
        return data;
    } catch (error) {
        console.error('Error stop simulation:', error);
        return false;
    }
}

export async function getPointLimit(deviceName: string, pointCode: string): Promise<PointLimit> {
    const pointLimit = {
        minValueLimit: 0,
        maxValueLimit: 0,
    };

    try {
        const data = await requestApi('/device/get_point_limit/', 'post', {
            device_name: deviceName,
            point_code: pointCode,
        });
        pointLimit.minValueLimit = data.min_value_limit;
        pointLimit.maxValueLimit = data.max_value_limit;
        return pointLimit;
    } catch (error) {
        console.error('Error stop simulation:', error);
        return pointLimit;
    }
}

export async function resetPointData(deviceName: string): Promise<boolean> {
    try {
        const data = await requestApi('/device/reset_point_data/', 'post', {
            device_name: deviceName,
        });
        return data;
    } catch (error) {
        console.error('Error stop simulation:', error);
        return false;
    }
}

export async function getPointInfo(deviceName: string, pointCode: string): Promise<any> {
    try {
        const data = await requestApi('/device/get_point_info', 'post', {
            device_name: deviceName,
            point_code: pointCode,
        });
        return data;
    } catch (error) {
        console.error('Error getting point info:', error);
        throw error;
    }
}

export async function setSinglePointSimulateMethod(deviceName: string, pointCode: string, simulateMethod: string): Promise<boolean> {
    try {
        const data = await requestApi('/device/set_single_point_simulate_method', 'post', {
            device_name: deviceName,
            point_code: pointCode,
            simulate_method: simulateMethod,
        });
        return data;
    } catch (error) {
        console.error('Error setting single point simulate method:', error);
        return false;
    }
}

export async function setSinglePointStep(deviceName: string, pointCode: string, step: number): Promise<boolean> {
    try {
        const data = await requestApi('/device/set_single_point_step', 'post', {
            device_name: deviceName,
            point_code: pointCode,
            step: step,
        });
        return data;
    } catch (error) {
        console.error('Error setting single point step:', error);
        return false;
    }
}

export async function setPointSimulationRange(deviceName: string, pointCode: string, minValue: number, maxValue: number): Promise<boolean> {
    try {
        const data = await requestApi('/device/set_point_simulation_range', 'post', {
            device_name: deviceName,
            point_code: pointCode,
            min_value: minValue,
            max_value: maxValue,
        });
        return data;
    } catch (error) {
        console.error('Error setting point simulation range:', error);
        return false;
    }
}

export async function editPointMetadata(deviceName: string, pointCode: string, metadata: any): Promise<boolean> {
    try {
        const data = await requestApi('/device/edit_point_metadata/', 'post', {
            device_name: deviceName,
            point_code: pointCode,
            metadata: metadata,
        });
        return data;
    } catch (error) {
        console.error('Error editing point metadata:', error);
        return false;
    }
}

// ===== 自动读取控制 =====

export async function getAutoReadStatus(deviceName: string): Promise<boolean> {
    try {
        const data = await requestApi('/device/get_auto_read_status', 'post', {
            device_name: deviceName,
        });
        return data;
    } catch (error) {
        console.error('Error getting auto read status:', error);
        return false;
    }
}

export async function startAutoRead(deviceName: string): Promise<boolean> {
    try {
        const data = await requestApi('/device/start_auto_read', 'post', {
            device_name: deviceName,
        });
        return data;
    } catch (error) {
        console.error('Error starting auto read:', error);
        return false;
    }
}

export async function stopAutoRead(deviceName: string): Promise<boolean> {
    try {
        const data = await requestApi('/device/stop_auto_read', 'post', {
            device_name: deviceName,
        });
        return data;
    } catch (error) {
        console.error('Error stopping auto read:', error);
        return false;
    }
}

export async function manualRead(deviceName: string, interval: number = 0): Promise<any> {
    try {
        const data = await requestApi('/device/manual_read', 'post', {
            device_name: deviceName,
            interval: interval
        });
        return data;
    } catch (error) {
        console.error('Error performing manual read:', error);
        return false;
    }
}

export async function readSinglePoint(deviceName: string, pointCode: string): Promise<number | null> {
    try {
        const data = await requestApi('/device/read_single_point', 'post', {
            device_name: deviceName,
            point_code: pointCode,
        });
        return data?.value ?? null;
    } catch (error) {
        console.error('Error reading single point:', error);
        return null;
    }
}

// ===== 报文捕获 =====

export interface MessageRecord {
    timestamp: number;
    formatted_time: string;
    direction: string;
    hex_data: string;
    raw_hex: string;
    description: string;
    length: number;
}

export async function getMessages(deviceName: string, limit: number = 100): Promise<MessageRecord[]> {
    try {
        const data = await requestApi('/device/get_messages', 'post', {
            device_name: deviceName,
            limit: limit,
        });
        return data?.messages ?? [];
    } catch (error) {
        console.error('Error getting messages:', error);
        return [];
    }
}

export async function clearMessages(deviceName: string): Promise<boolean> {
    try {
        const data = await requestApi('/device/clear_messages', 'post', {
            device_name: deviceName,
        });
        return data;
    } catch (error) {
        console.error('Error clearing messages:', error);
        return false;
    }
}

export interface AvgTimeStats {
    tx_count: number;
    rx_count: number;
    total_count: number;
    pair_count: number;
    avg_latency_ms: number;
}

export async function getAvgTime(deviceName: string): Promise<AvgTimeStats | null> {
    try {
        const data = await requestApi('/device/get_avg_time', 'post', {
            device_name: deviceName,
        });
        return data;
    } catch (error) {
        console.error('Error getting avg time:', error);
        return null;
    }
}

// ===== 动态测点/从机管理 =====

export interface PointCreateData {
    frame_type: number;  // 0=遥测, 1=遥信, 2=遥控, 3=遥调
    code: string;
    name: string;
    rtu_addr: number;
    reg_addr: string;
    func_code: number;
    decode_code: string;
    mul_coe: number;
    add_coe: number;
}

export async function addPoint(deviceName: string, pointData: PointCreateData): Promise<boolean> {
    try {
        const data = await requestApi('/device/add_point', 'post', {
            device_name: deviceName,
            ...pointData,
        });
        return data;
    } catch (error) {
        console.error('Error adding point:', error);
        return false;
    }
}

export async function addPointsBatch(deviceName: string, frameType: number, points: PointCreateData[]): Promise<boolean> {
    try {
        const data = await requestApi('/device/add_points_batch', 'post', {
            device_name: deviceName,
            frame_type: frameType,
            points: points,
        });
        return data;
    } catch (error) {
        console.error('Error adding points batch:', error);
        return false;
    }
}

export async function deletePoint(deviceName: string, pointCode: string): Promise<boolean> {
    try {
        const data = await requestApi('/device/delete_point', 'post', {
            device_name: deviceName,
            point_code: pointCode,
        });
        return data;
    } catch (error) {
        console.error('Error deleting point:', error);
        return false;
    }
}

export async function addSlave(deviceName: string, slaveId: number): Promise<boolean> {
    try {
        const data = await requestApi('/device/add_slave', 'post', {
            device_name: deviceName,
            slave_id: slaveId,
        });
        return data;
    } catch (error) {
        console.error('Error adding slave:', error);
        return false;
    }
}

export async function deleteSlave(deviceName: string, slaveId: number): Promise<boolean> {
    try {
        const data = await requestApi('/device/delete_slave', 'post', {
            device_name: deviceName,
            slave_id: slaveId,
        });
        return data;
    } catch (error) {
        console.error('Error deleting slave:', error);
        return false;
    }
}

export async function editSlave(deviceName: string, oldSlaveId: number, newSlaveId: number): Promise<boolean> {
    try {
        const data = await requestApi('/device/edit_slave', 'post', {
            device_name: deviceName,
            old_slave_id: oldSlaveId,
            new_slave_id: newSlaveId,
        });
        return data;
    } catch (error) {
        console.error('Error editing slave:', error);
        return false;
    }
}

export async function clearPoints(deviceName: string, slaveId: number): Promise<number> {
    try {
        const data = await requestApi('/device/clear_points', 'post', {
            device_name: deviceName,
            slave_id: slaveId,
        });
        return data;
    } catch (error) {
        console.error('Error clearing points:', error);
        return 0;
    }
}