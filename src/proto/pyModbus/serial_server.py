import modbus_tk.defines as cst
from modbus_tk import modbus_rtu
import serial
import threading
from src.config.log.logger import Log

import logging

# 获取pymodbus的日志记录器
logger = logging.getLogger('modbus_tk')
# 设置日志级别
logger.setLevel(logging.ERROR)


class ModbusSerialServer:
    def __init__(self):
        self.port = '/dev/ttyS1'
        self.baud_rate = 9600
        self.data_bits = 8
        self.parity = 'N'
        self.stop_bits = 1
        self.timeout = 10
        self.server = None
        self.stop_event = threading.Event()
        self.logger = Log(filename='../log/serial.log', mode='a', cmdlevel='ERROR', filelevel='DEBUG',
                       limit=2048000, backup_count=10, when='D', colorful=True)
        
    def setConfig(self, port, baud_rate, data_bits, parity, stop_bits, timeout=10):
        self.port = port
        self.baud_rate = baud_rate
        self.data_bits = data_bits
        self.parity = parity
        self.stop_bits = stop_bits
        self.timeout = timeout
    
    def initServer(self):
        try:
            # 设置串口
            server = serial.Serial(port=self.port, baudrate=self.baud_rate, bytesize=self.data_bits, parity=self.parity, stopbits=self.stop_bits, timeout=self.timeout)
            self.server = modbus_rtu.RtuServer(server)
            # 初始化主从机
            self.initSlaves()
            self.logger.info("modbusSerial server running...")
        except Exception as e:
            self.logger.error("initServer error: " + str(e))
    
    def handle(self):
        self.server.start()
    
    def startServer(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.handle)
        self.thread.start()

    def stopServer(self):
        self._logger.info("停止运行modbus_serial_server线程")
        if self.stop_event is not None:
            self.stop_event.set()
        if self.thread is not None:
            self.thread.join()

    def isRunning(self):
        if self.thread is not None and self.thread.is_alive():
            return True
        else:
            return False
    
    # 初始化主从机
    def initSlaves(self):
        # 默认设置12个从机
        for slave_id in range(1, 12):
            slave = self.server.add_slave(slave_id)
            slave_name = 'slave_' + str(slave_id)+'_'
            slave.add_block(slave_name + 'coils', cst.COILS, 0, 65535)
            slave.add_block(slave_name + 'discrete_inputs', cst.DISCRETE_INPUTS, 0, 65535)
            slave.add_block(slave_name + 'inputs', cst.ANALOG_INPUTS, 0, 65535)
            slave.add_block(slave_name + 'holdings', cst.HOLDING_REGISTERS, 0, 65535)
    
    def setValueByAddress(self, func_code, slave_id, address, value):
        slave = self.server.get_slave(int(slave_id))
        slave_name = 'slave_' + str(slave_id) + '_'
        if func_code == "4":
            slave.set_values(slave_name + 'inputs', address, value)
        elif func_code == "3" or func_code == "6":
            slave.set_values(slave_name + 'holdings', address, value)
            
    # 业务部分
    def setAllRegisterValues(self, yc_dict, yx_dict):
        for slave_id in range(0, len(yc_dict)):
            yc_list = yc_dict.get(slave_id)
            # 将遥测数据写入到寄存器中
            for i in range(0, len(yc_list)):
                self.setValueByAddress(yc_list[i].func_code, yc_list[i].rtu_addr, yc_list[i].address,
                                       yc_list[i].value)

        for slave_id in range(0, len(yx_dict)):
            yx_list = yx_dict.get(slave_id)
            # 将遥信数据写入到寄存器中
            for i in range(0, len(yx_list)):
                self.setValueByAddress(yx_list[i].func_code, yx_list[i].rtu_addr, yx_list[i].address, yx_list[i].value)
                
    