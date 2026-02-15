import sys
import os
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.data.dao.point_mapping_dao import PointMappingDao
from src.data.model.point_mapping import PointMapping

def test_crud():
    print("Testing PointMappingDao CRUD...")
    
    # 1. Create
    mapping_data = {
        "target_point_code": "TEST_T_001",
        "source_point_codes": '["TEST_S_001", "TEST_S_002"]',
        "formula": "TEST_S_001 + TEST_S_002",
        "enable": True
    }
    
    print("Creating mapping...")
    mapping = PointMappingDao.create_mapping(mapping_data)
    if mapping:
        print(f"Created mapping: {mapping.id}, {mapping.target_point_code}")
    else:
        print("Failed to create mapping")
        return

    mapping_id = mapping.id

    # 2. Read
    print("Reading mapping by ID...")
    read_mapping = PointMappingDao.get_mapping_by_id(mapping_id)
    if read_mapping:
        print(f"Read mapping: {read_mapping.id}, {read_mapping.target_point_code}")
        assert read_mapping.target_point_code == "TEST_T_001"
    else:
        print("Failed to read mapping")
        return

    print("Reading all mappings...")
    all_mappings = PointMappingDao.get_all_mappings()
    print(f"Total mappings: {len(all_mappings)}")
    found = False
    for m in all_mappings:
        if m.id == mapping_id:
            found = True
            break
    if found:
        print("Found created mapping in all mappings")
    else:
        print("Failed to find created mapping in all mappings")
        return

    # 3. Update
    print("Updating mapping...")
    update_data = {"formula": "TEST_S_001 * TEST_S_002", "enable": False}
    success = PointMappingDao.update_mapping(mapping_id, update_data)
    if success:
        print("Update successful")
        updated_mapping = PointMappingDao.get_mapping_by_id(mapping_id)
        print(f"Updated mapping formula: {updated_mapping.formula}, enable: {updated_mapping.enable}")
        assert updated_mapping.formula == "TEST_S_001 * TEST_S_002"
        assert updated_mapping.enable == False
    else:
        print("Update failed")
        return

    # 4. Delete
    print("Deleting mapping...")
    success = PointMappingDao.delete_mapping(mapping_id)
    if success:
        print("Delete successful")
        deleted_mapping = PointMappingDao.get_mapping_by_id(mapping_id)
        if deleted_mapping is None:
            print("Mapping confirmed deleted")
        else:
            print("Mapping still exists after delete")
    else:
        print("Delete failed")

if __name__ == "__main__":
    try:
        test_crud()
        print("DAO Test Completed Successfully")
    except Exception as e:
        print(f"Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
