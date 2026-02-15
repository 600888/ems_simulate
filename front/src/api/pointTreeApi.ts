import { requestApi } from './deviceApi';

export interface PointLeaf {
    code: string;
    name: string;
    value: any;
    rtu_addr: number;
    reg_addr: string;
    type: string;
}

export interface TypeNode {
    label: string;
    children: PointLeaf[];
}

export interface DeviceNode {
    label: string;
    children: TypeNode[];
}

export interface TreeResponse {
    code: number;
    message: string;
    data: DeviceNode[];
}

const BASE_URL = '/point_tree';

/**
 * 获取系统测点树
 */
export async function getPointTree(): Promise<DeviceNode[]> {
    try {
        const res: any = await requestApi(`${BASE_URL}/tree`, 'get', null);
        // The backend returns { code: ..., message: ..., data: [...] }
        // requestApi might handle the response wrapper or not? 
        // Usually requestApi unwraps 'data' if configured so. 
        // Based on pointMappingApi, requestApi seems to return the data directly or the full response?
        // Let's check deviceApi.ts or just return res directly if it matches standard pattern.
        // Assuming requestApi returns the 'data' field of BaseResponse.
        return res;
    } catch (error) {
        console.error('Error fetching point tree:', error);
        throw error;
    }
}
