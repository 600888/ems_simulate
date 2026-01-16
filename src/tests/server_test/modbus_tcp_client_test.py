import unittest

from src.pyModbus.modbus_tk.tcp_client import ModbusTcpClient


class ModbusTcpClientTest(unittest.TestCase):
    def test_init_client(self):
        modbus_client = ModbusTcpClient(address="10.10.111.54", port=10502)
        self.assertIsNotNone(modbus_client)

    def test_read_register_values(self):
        modbus_client = ModbusTcpClient(address="10.10.111.54", port=10502)
        value = modbus_client.read_register_values(4, 1, 4125)
        print(value)

    def test_write_register_values(self):
        modbus_client = ModbusTcpClient(address="10.10.111.54", port=10503)
        value = modbus_client.write_register_values(6, 1, 1024, 8691)
        print(value)