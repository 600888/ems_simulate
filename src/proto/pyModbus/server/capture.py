from pymodbus.framer.socket_framer import ModbusSocketFramer
from pymodbus.framer.rtu_framer import ModbusRtuFramer

def CreateCaptureSocketFramer(message_capture):
    class CaptureSocketFramer(ModbusSocketFramer):
        def processIncomingPacket(self, data, callback, *args, **kwargs):
            if data and message_capture:
                message_capture.add_rx(data)
            return super().processIncomingPacket(data, callback, *args, **kwargs)

        def buildPacket(self, message):
            data = super().buildPacket(message)
            if data and message_capture:
                message_capture.add_tx(data)
            return data
    return CaptureSocketFramer

def CreateCaptureRtuFramer(message_capture):
    class CaptureRtuFramer(ModbusRtuFramer):
        def processIncomingPacket(self, data, callback, *args, **kwargs):
            # RTU framer appends data to buffer; interception point might differ
            # But processIncomingPacket is where data is fed.
            # However, RTU framer might be fed byte by byte.
            # Ideally we capture what is fed to it.
            if data and message_capture:
                message_capture.add_rx(data)
            return super().processIncomingPacket(data, callback, *args, **kwargs)

        def buildPacket(self, message):
            data = super().buildPacket(message)
            if data and message_capture:
                message_capture.add_tx(data)
            return data
    return CaptureRtuFramer
