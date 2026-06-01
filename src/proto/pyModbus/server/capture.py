from pymodbus.framer import FramerRTU, FramerSocket


def CreateCaptureSocketFramer(message_capture):
    """创建带报文捕获功能的 Socket Framer 类"""

    class CaptureSocketFramer(FramerSocket):
        def handleFrame(self, data, exp_devid, exp_tid):
            if data and message_capture:
                message_capture.add_rx(data)
            return super().handleFrame(data, exp_devid, exp_tid)

        def buildFrame(self, message):
            data = super().buildFrame(message)
            if data and message_capture:
                message_capture.add_tx(data)
            return data

    return CaptureSocketFramer


def CreateCaptureRtuFramer(message_capture):
    """创建带报文捕获功能的 RTU Framer 类"""

    class CaptureRtuFramer(FramerRTU):
        def handleFrame(self, data, exp_devid, exp_tid):
            if data and message_capture:
                message_capture.add_rx(data)
            return super().handleFrame(data, exp_devid, exp_tid)

        def buildFrame(self, message):
            data = super().buildFrame(message)
            if data and message_capture:
                message_capture.add_tx(data)
            return data

    return CaptureRtuFramer
