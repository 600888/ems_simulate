import unittest

from src.pyModbus.server import ModbusServer


class ModbusServerTest(unittest.TestCase):
    def test_init_server(self):
        modbus_server = ModbusServer()
        modbus_server.initServer()
        self.assertIsNotNone(modbus_server.server)

    def test_start_server(self):
        modbus_server = ModbusServer()
        modbus_server.initServer()
        modbus_server.startServer()
        self.assertIsNotNone(modbus_server.server)
        value = modbus_server.getValueByAddress(5, 1, 1)
        print(value)
