"""Diagnostic: Test GoCB discovery WITHOUT GOOSE publishing (MMS only)"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_gocb_result.txt")

def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    sys.stdout.flush()

with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("")

import pyiec61850.pyiec61850 as iec61850

log("=== Building model programmatically ===")
model = iec61850.IedModel_create("TESTIED")
ld = iec61850.LogicalDevice_create("LD0", model)
lln0 = iec61850.LogicalNode_create("LLN0", ld)
ggio1 = iec61850.LogicalNode_create("GGIO1", ld)

do1 = iec61850.DataObject_create("Ind1", iec61850.toModelNode(ggio1), 0)
da1 = iec61850.DataAttribute_create(
    "stVal", iec61850.toModelNode(do1),
    iec61850.IEC61850_BOOLEAN, iec61850.IEC61850_FC_ST, 0, 0, 0
)

ds = iec61850.DataSet_create("dsGOOSE1", lln0)
ds_entry = iec61850.DataSetEntry_create(ds, "LD0/GGIO1$ST$Ind1$stVal", 0, None)

gcb = iec61850.GSEControlBlock_create(
    "gcb1", lln0, "0001", "dsGOOSE1", 1, False, 10, 1000
)
log(f"Model built: GoCB={'OK' if gcb else 'FAIL'}")

# Verify model
ds_ref = iec61850.IedModel_lookupDataSet(model, "TESTIEDLD0/LLN0$dsGOOSE1")
log(f"DataSet lookup: {'FOUND' if ds_ref else 'NOT FOUND'}")

log("")
log("=== Creating IedServer (NO GOOSE publishing) ===")
server = iec61850.IedServer_create(model)
log(f"IedServer_create: {'OK' if server else 'FAIL'}")

if server:
    # SKIP setGooseInterfaceId and enableGoosePublishing
    # These require raw Ethernet which Windows doesn't support
    log("Skipping GOOSE publishing (not needed for MMS discovery)")
    
    log("Starting MMS server...")
    iec61850.IedServer_start(server, 102)
    
    is_running = iec61850.IedServer_isRunning(server)
    log(f"is_running: {is_running}")
    
    if is_running:
        log("")
        log("SUCCESS: MMS server running on port 102")
        log("  GoCB 'gcb1' should be discoverable via IEDScout MMS browser")
        log("  Navigate: Server > LD0 > LLN0 > GoCB")
        log("  Waiting 8 seconds for IEDScout test...")
        time.sleep(8)
        
        iec61850.IedServer_stop(server)
        iec61850.IedServer_destroy(server)
        log("Server stopped")
    else:
        log("FAIL: Server not running")

log("Test completed")
