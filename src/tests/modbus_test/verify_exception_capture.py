import unittest
from unittest.mock import MagicMock
from pymodbus.pdu import ExceptionResponse, ModbusRequest
from src.proto.pyModbus.client.capture import ModbusTcpClientWithCapture
from src.device.core.message_capture import MessageCapture

class TestModbusExceptionCapture(unittest.TestCase):
    def test_capture_exception_response(self):
        # Setup
        message_capture = MessageCapture()
        client = ModbusTcpClientWithCapture(host='127.0.0.1', message_capture=message_capture)
        
        # Mock request
        request = MagicMock(spec=ModbusRequest)
        request.function_code = 0x03
        request.slave_id = 1
        request.encode.return_value = b'\x00\x00' # Dummy encode

        # Mock super().execute to return ExceptionResponse
        # Exception Code 2: Illegal Data Address
        exception_response = ExceptionResponse(0x03, 0x02) 
        
        # We need to mock the super().execute method. 
        # Since we can't easily patch super(), we'll patch the client's execute method 
        # but we actually want to test the logic INSIDE execute.
        # So we will mock the parent class 'ModbusTcpClient.execute'
        
        with unittest.mock.patch('pymodbus.client.ModbusTcpClient.execute') as mock_super_execute:
            mock_super_execute.return_value = exception_response
            
            # Action
            client.execute(request)
            
            # Assert
            messages = message_capture.get_messages()
            self.assertEqual(len(messages), 2, "Should capture both TX and RX")
            
            rx_msg = messages[1]
            self.assertEqual(rx_msg['direction'], "RX")
            
            # Check RX data sequence
            # MBAP (7 bytes) + Function Code (1 byte) + Exception Code (1 byte)
            # Function code for exception is Original + 0x80 -> 0x03 + 0x80 = 0x83
            # Exception code = 0x02
            # Length in MBAP should be 3 (UnitID + FC + EC) => UnitID(1) + 1 + 1 = 3
            
            rx_data = bytes.fromhex(rx_msg['data'])
            
            # Verify Function Code (byte 7 in MBAP+PDU)
            # MBAP: [TID][TID][PID][PID][LEN][LEN][UID]
            #        0    1    2    3    4    5    6
            # PDU:  [FC] [EC]
            #        7    8
            
            self.assertEqual(rx_data[7], 0x83, "Should have exception function code 0x83")
            self.assertEqual(rx_data[8], 0x02, "Should have exception code 0x02")

if __name__ == '__main__':
    unittest.main()
