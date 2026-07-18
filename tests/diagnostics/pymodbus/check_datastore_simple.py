try:
    from pymodbus.datastore import ModbusSlaveContext

    print("ModbusSlaveContext exists")
except ImportError:
    print("ModbusSlaveContext does NOT exist")
    try:
        from pymodbus.datastore import ModbusDeviceContext

        print("ModbusDeviceContext exists")
    except ImportError:
        print("ModbusDeviceContext does NOT exist")
