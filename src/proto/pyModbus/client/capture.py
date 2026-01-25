import struct
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.framer import Framer, ModbusRtuFramer
from pymodbus.pdu import ModbusRequest
from src.device.core.message_capture import MessageCapture

def computeCRC(data):
    """计算CRC16"""
    crc = 0xFFFF
    for i in range(len(data)):
        crc ^= data[i]
        for _ in range(8):
            if (crc & 0x0001):
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc

class ModbusTcpClientWithCapture(ModbusTcpClient):
    def __init__(self, host: str, port: int = 502, message_capture=None):
        super().__init__(host=host, port=port, framer=Framer.SOCKET)
        self.message_capture = message_capture

    def execute(self, request: ModbusRequest):
        # 构造PDU（功能码 + 数据）
        try:
            pdu = bytes([request.function_code]) + request.encode()

            # 构造MBAP头部
            # 注意: self.transaction 在 pymodbus 不同版本中可能不同，这里假设是 standard
            transaction_id = self.transaction.getNextTID() & 0xFFFF
            protocol_id = 0x0000
            length = len(pdu) + 1  # PDU长度 + 从机ID
            unit_id = request.slave_id

            mbap_header = bytearray([
                (transaction_id >> 8) & 0xFF,
                transaction_id & 0xFF,
                (protocol_id >> 8) & 0xFF,
                protocol_id & 0xFF,
                (length >> 8) & 0xFF,
                length & 0xFF,
                unit_id,
            ])

            # 完整报文
            full_request = mbap_header + pdu
            # 记录请求
            if self.message_capture:
                self.message_capture.add_tx(full_request)
        except Exception as e:
            pass

        # 执行请求
        response = super().execute(request)

        # 处理响应
        try:
            if response and not response.isError():
                response_pdu = bytes([response.function_code]) + response.encode()
                response_mbap_header = bytearray([
                    (transaction_id >> 8) & 0xFF,
                    transaction_id & 0xFF,
                    (protocol_id >> 8) & 0xFF,
                    protocol_id & 0xFF,
                    (len(response_pdu) >> 8) & 0xFF,
                    len(response_pdu) & 0xFF,
                    unit_id,
                ])
                full_response = response_mbap_header + response_pdu
                # 记录响应
                if self.message_capture:
                     self.message_capture.add_rx(full_response)
        except Exception as e:
            pass
            
        return response

class ModbusSerialClientWithCapture(ModbusSerialClient):
    def __init__(self, port, baudrate, bytesize, parity, stopbits, message_capture=None):
        super().__init__(port=port, baudrate=baudrate, bytesize=bytesize, parity=parity, stopbits=stopbits, framer=ModbusRtuFramer)
        self.message_capture = message_capture

    def execute(self, request: ModbusRequest):
        # 构造 RTU 报文: Slave ID + PDU + CRC
        try:
            pdu = bytes([request.function_code]) + request.encode()
            unit_id = request.slave_id
            
            # Slave + PDU
            pre_crc = bytes([unit_id]) + pdu
            
            # CRC (Little Endian for Modbus)
            crc = computeCRC(pre_crc)
            crc_bytes = struct.pack('<H', crc)
            
            full_request = pre_crc + crc_bytes
            
            # 记录请求
            if self.message_capture:
                self.message_capture.add_tx(full_request)
        except Exception as e:
            pass

        # 执行请求
        response = super().execute(request)

        # 处理响应
        try:
            if response and not response.isError():
                response_pdu = bytes([response.function_code]) + response.encode()
                
                # Reconstruct response frame for logging (Slave + PDU + CRC)
                pre_crc_resp = bytes([unit_id]) + response_pdu
                crc_resp = computeCRC(pre_crc_resp)
                crc_bytes_resp = struct.pack('<H', crc_resp)
                
                full_response = pre_crc_resp + crc_bytes_resp
                
                # 记录响应
                if self.message_capture:
                     self.message_capture.add_rx(full_response)
        except Exception as e:
            pass
            
        return response

class ModbusRtuOverTcpClientWithCapture(ModbusTcpClient):
    def __init__(self, host: str, port: int = 502, message_capture=None):
        super().__init__(host=host, port=port, framer=ModbusRtuFramer)
        self.message_capture = message_capture

    def execute(self, request: ModbusRequest):
        # 构造 RTU Over TCP 报文 (同 RTU)
        try:
            pdu = bytes([request.function_code]) + request.encode()
            unit_id = request.slave_id
            
            pre_crc = bytes([unit_id]) + pdu
            
            crc = computeCRC(pre_crc)
            crc_bytes = struct.pack('<H', crc)
            
            full_request = pre_crc + crc_bytes
            
            # 记录请求
            if self.message_capture:
                self.message_capture.add_tx(full_request)
        except Exception as e:
            pass

        # 执行请求
        response = super().execute(request)

        # 处理响应
        try:
            if response and not response.isError():
                response_pdu = bytes([response.function_code]) + response.encode()
                
                pre_crc_resp = bytes([unit_id]) + response_pdu
                crc_resp = computeCRC(pre_crc_resp)
                crc_bytes_resp = struct.pack('<H', crc_resp)
                
                full_response = pre_crc_resp + crc_bytes_resp
                
                # 记录响应
                if self.message_capture:
                     self.message_capture.add_rx(full_response)
        except Exception as e:
            pass
            
        return response
