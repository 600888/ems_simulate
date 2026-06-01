import pymodbus.framer

print("Contents of pymodbus.framer:")
for item in dir(pymodbus.framer):
    print(item)

try:
    from pymodbus.framer import Framer

    print("Framer found!")
except ImportError:
    print("Framer NOT found")
