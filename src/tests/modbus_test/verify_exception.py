from pymodbus.pdu import ExceptionResponse

# Function code 3 (Read Holding Registers), Exception Code 2 (Illegal Data Address)
e = ExceptionResponse(0x03, 0x02) 

print(f"Original Function code passed: 0x03")
print(f"Object Function code: {e.function_code} (Hex: {hex(e.function_code)})")
print(f"Exception code: {e.exception_code}")
print(f"Is Error: {e.isError()}")
print(f"Encoded: {e.encode().hex()}")

# Check if we need to manually add 0x80 to function code for the PDU
# Standard Modbus Exception PDU: [Function Code | 0x80] [Exception Code]
