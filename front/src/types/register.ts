export interface IntPointRegister {
    signed: number;
    unsigned: number;
    hex: string;
    bin: string;
    real: number;
    mulCoe: number;
    addCoe: number;
}

export interface LongPointRegister {
    longABCD: number,  // 原始顺序 (ABCD)
    longCDAB: number,  // 高低16位交换 (CDAB)
    longBADC: number,  // 字节内高低字节交换 (BADC)
    longDCBA: number,  // 完全逆序 (DCBA)
    real: number;
    mulCoe: number;
    addCoe: number;
}

export interface FloatPointRegister {
    floatABCD: number;  // 原始顺序 (ABCD)
    floatCDAB: number;  // 高低16位交换 (CDAB)
    floatBADC: number;  // 字节内高低字节交换 (BADC)
    floatDCBA: number;  // 完全逆序 (DCBA)
    real: number;
    mulCoe: number;
    addCoe: number;
}