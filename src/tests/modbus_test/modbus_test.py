from pymodbus.client import ModbusTcpClient
from datetime import datetime


class DebugModbusTcpClient(ModbusTcpClient):
    def execute(self, request):
        # 获取 Modbus 请求的 PDU（应用层数据）
        pdu = request.encode()

        # 构造完整的 Modbus TCP 报文（MBAP + PDU）
        transaction_id = self.transaction.getNextTID()  # 获取事务 ID
        protocol_id = 0x0000  # Modbus TCP 协议 ID
        length = len(pdu) + 1  # PDU 长度 + 单元标识符（slave ID）
        unit_id = request.slave_id  # 单元标识符（slave ID）

        # 构造 MBAP 头部
        mbap_header = bytearray(
            [
                (transaction_id >> 8) & 0xFF,  # 事务 ID 高字节
                transaction_id & 0xFF,  # 事务 ID 低字节
                (protocol_id >> 8) & 0xFF,  # 协议 ID 高字节
                protocol_id & 0xFF,  # 协议 ID 低字节
                (length >> 8) & 0xFF,  # 长度高字节
                length & 0xFF,  # 长度低字节
                unit_id,  # 单元标识符
            ]
        )

        # 完整的 Modbus TCP 报文（MBAP + PDU）
        full_request = mbap_header + pdu

        # 打印发送的完整报文（16进制格式）
        request_hex = " ".join(f"{b:02x}" for b in full_request)
        send_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 获取当前时间
        print(f"[{send_time}]TX: {request_hex}")

        # 执行请求并获取响应
        response = super().execute(request)

        # 打印接收的完整报文（16进制格式）并记录时间
        if response:
            # 获取响应的 PDU
            response_pdu = response.encode()

            # 构造完整的 Modbus TCP 响应报文（MBAP + PDU）
            response_mbap_header = bytearray(
                [
                    (transaction_id >> 8) & 0xFF,  # 事务 ID 高字节
                    transaction_id & 0xFF,  # 事务 ID 低字节
                    (protocol_id >> 8) & 0xFF,  # 协议 ID 高字节
                    protocol_id & 0xFF,  # 协议 ID 低字节
                    (len(response_pdu) + 1 >> 8) & 0xFF,  # 长度高字节
                    (len(response_pdu) + 1) & 0xFF,  # 长度低字节
                    unit_id,  # 单元标识符
                ]
            )

            # 完整的 Modbus TCP 响应报文（MBAP + PDU）
            full_response = response_mbap_header + response_pdu

            # 打印接收的完整报文（16进制格式）并记录时间
            response_hex = " ".join(f"{b:02x}" for b in full_response)
            receive_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 获取当前时间
            print(f"[{receive_time}]RX: {response_hex}")

        return response


# 使用自定义的调试客户端
client = DebugModbusTcpClient("10.10.112.5", port=10505)

# 建立连接
connection = client.connect()

if connection:
    print("连接成功")
else:
    print("连接失败")

# 读取保持寄存器
if __name__ == "__main__":
    while True:
        result1 = client.read_input_registers(slave=1, address=100, count=10)
        result2 = client.read_holding_registers(slave=3, address=1, count=100)
        result3 = client.read_holding_registers(slave=1, address=1, count=10)
