"""
Diagnostic test: Use IEC61850Server class (same as application code) to test GoCB discovery
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pyiec61850.pyiec61850 as iec61850

from src.proto.iec61850.iec61850_server import IEC61850Server

print("=" * 60)
print("Test: IEC61850Server with GoCB (same as application code)")
print("=" * 60)

# 1. Create server instance (same as app code)
server = IEC61850Server(port=10102, model_name="TestIED", ld_name="LD0")
print("IEC61850Server created: port=10102, model=TestIED, ld=LD0")

# 2. Add some points (simulate ICD import)
points = [
    ("LD0/GGIO1.Ind1.stVal", 1, "ST"),  # YX
    ("LD0/GGIO1.Ind2.stVal", 1, "ST"),  # YX
    ("LD0/MMXU1.Vol.mag.f", 0, "MX"),  # YC
]
for addr, ft, fc in points:
    ref = server.add_point(addr, ft, fc)
    print(f"  add_point('{addr}'): ref={ref}")

# 3. Add GOOSE control block (same as app code)
entries = [
    {"name": "LD0/GGIO1.Ind1.stVal", "value": True, "iec_type": "boolean"},
    {"name": "LD0/GGIO1.Ind2.stVal", "value": True, "iec_type": "boolean"},
]

result = server.add_goose_control_block(
    name="gcb1",
    app_id=0x0001,
    data_set_ref="LD0/LLN0$dsGOOSE1",
    conf_rev=1,
    go_id="TestIEDgcb1",
    min_time=10,
    max_time=1000,
    ld_inst="LD0",
    entries=entries,
)
print(f"\nadd_goose_control_block: result={result}")
print(f"  _goose_cb_list: {server._goose_cb_list}")
print(f"  _dataset_catalog: {len(server._dataset_catalog)} entries")
print(f"  _ld_map keys: {list(server._ld_map.keys())}")
print(f"  _ln_map keys: {list(server._ln_map.keys())}")

# 4. Verify DataSet lookup in the model
print("\n--- DataSet Verification ---")
for ref in [
    "LD0/LLN0$dsGOOSE1",
    "TestIEDLD0/LLN0$dsGOOSE1",
    f"{server.model_name}LD0/LLN0$dsGOOSE1",
]:
    ds = iec61850.IedModel_lookupDataSet(server._model, ref)
    print(f"  lookupDataSet('{ref}'): {'FOUND' if ds else 'NOT FOUND'}")

# 5. Start the server
print("\n--- Starting Server ---")
server.start()
print(f"  is_running: {server.is_running}")
print(f"  _server: {server._server is not None}")

if server.is_running:
    # 6. Verify model structure
    print("\n--- Post-start Verification ---")
    print(f"  _goose_cb_list: {len(server._goose_cb_list)} GoCBs")
    print(f"  _point_attrs: {len(server._point_attrs)} DataAttributes")

    # 7. Test point read/write (basic MMS functionality)
    val = server.get_point_value("LD0/GGIO1.Ind1.stVal")
    print(f"  get_point_value('LD0/GGIO1.Ind1.stVal'): {val}")

    print("\n" + "=" * 60)
    print("[SUCCESS] Server running on port 10102")
    print("  -> Connect IEDScout to <local-ip>:10102")
    print("  -> Navigate to LD0 > LLN0 to find GoCB 'gcb1'")
    print("  -> Press Ctrl+C to stop")
    print("=" * 60)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")

    server.stop()
else:
    print("\n[FAIL] Server did not start!")

print("Test completed")
