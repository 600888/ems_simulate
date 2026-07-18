try:
    import pymodbus.device

    print("Imported pymodbus.device")
    from pymodbus.device import ModbusDeviceIdentification

    print("Imported ModbusDeviceIdentification")
except ImportError as e:
    print(f"Error importing pymodbus.device: {e}")
except Exception as e:
    print(f"Other error: {e}")
