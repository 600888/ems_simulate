# PyInstaller runtime hook: patch numpy 2.x compatibility for openpyxl
# openpyxl 3.1.x references numpy.short/ushort/etc. which were removed in numpy 2.0
import numpy

_ALIASES = {
    "short": "int16",
    "ushort": "uint16",
    "intc": "int32",
    "uintc": "uint32",
    "int_": "intp",
    "uint": "uintp",
    "longlong": "longlong",
    "ulonglong": "ulonglong",
    "half": "float16",
    "single": "float32",
    "double": "float64",
    "longdouble": "longdouble",
    "intp": "intp",
    "uintp": "uintp",
    "bool_": "bool_",
    "floating": "floating",
    "integer": "integer",
}

for alias, target in _ALIASES.items():
    if not hasattr(numpy, alias) and hasattr(numpy, target):
        setattr(numpy, alias, getattr(numpy, target))
