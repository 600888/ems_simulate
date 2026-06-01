try:
    from src.proto.pyModbus.helper import get_commandline

    print("Successfully imported helper")
except ImportError as e:
    print(f"Error importing helper: {e}")
