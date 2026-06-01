import pymodbus.pdu

print("pymodbus.pdu contents:")
for item in dir(pymodbus.pdu):
    if "Read" in item or "Write" in item or "Request" in item or "Response" in item:
        print(item)
