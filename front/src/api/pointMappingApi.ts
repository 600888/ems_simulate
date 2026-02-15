import { requestApi } from './deviceApi';

export interface PointMapping {
    id: number;
    device_name: string;
    target_point_code: string;
    source_point_codes: string; // JSON string from backend
    formula: string;
    enable: boolean;
}

export interface PointMappingCreate {
    device_name: string;
    target_point_code: string;
    source_point_codes: any[]; // Changed to any[] or specific struct
    formula: string;
    enable: boolean;
}

export interface PointMappingUpdate {
    device_name?: string;
    target_point_code?: string;
    source_point_codes?: any[];
    formula?: string;
    enable?: boolean;
}

const BASE_URL = '/point_mapping';

/**
 * 获取所有映射
 */
export async function getMappings(): Promise<PointMapping[]> {
    try {
        const data = await requestApi(`${BASE_URL}/list`, 'get', null);
        return data;
    } catch (error) {
        console.error('Error fetching mappings:', error);
        throw error;
    }
}

/**
 * 创建映射
 */
export async function createMapping(data: PointMappingCreate): Promise<PointMapping> {
    try {
        const res = await requestApi(`${BASE_URL}/create`, 'post', data);
        return res;
    } catch (error) {
        console.error('Error creating mapping:', error);
        throw error;
    }
}

/**
 * 更新映射
 */
export async function updateMapping(id: number, data: PointMappingUpdate): Promise<boolean> {
    try {
        const body = { id, ...data };
        const res = await requestApi(`${BASE_URL}/update`, 'post', body);
        return res;
    } catch (error) {
        console.error('Error updating mapping:', error);
        throw error;
    }
}

/**
 * 删除映射
 */
export async function deleteMapping(id: number): Promise<boolean> {
    try {
        const res = await requestApi(`${BASE_URL}/delete`, 'post', { mapping_id: id });
        return res;
    } catch (error) {
        console.error('Error deleting mapping:', error);
        throw error;
    }
}
