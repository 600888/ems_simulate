import pyiec61850.pyiec61850 as iec61850


def list_functions(module, pattern="IedConnection_"):
    funcs = [f for f in dir(module) if f.startswith(pattern)]
    for f in sorted(funcs):
        print(f)


if __name__ == "__main__":
    print("Available IedConnection functions:")
    list_functions(iec61850)
