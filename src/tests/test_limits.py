import json
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.dao.point_dao import PointDao
from src.enums.modbus_register import Decode


def test_limits_calculation():
    # 0x21 - INT16_BE (-32768, 32767)
    point_data = {
        "code": "TEST_YC_01",
        "name": "测试测点01",
        "rtu_addr": 1,
        "reg_addr": "0x0001",
        "func_code": 3,
        "decode_code": "0x21",
        "mul_coe": 1.0,
        "add_coe": 0.0,
    }

    # Need an existing channel ID, let's just make sure limits calculation is hit in Dao logic
    try:
        from src.data.controller.db import local_session
        from src.data.model.channel import Channel

        with local_session() as session, session.begin():
            ch = Channel(name="Test Channel", proto_name="ModbusTcp", ip="127.0.0.1", port=502)
            session.add(ch)
            session.flush()
            channel_id = ch.id

            # Test Yc creation
            res_yc = PointDao.create_yc(channel_id, point_data)
            print(f"Yc max/min (0x21, 1.0, 0.0): {res_yc['max_limit']} / {res_yc['min_limit']}")
            assert res_yc["max_limit"] == 32767.0
            assert res_yc["min_limit"] == -32768.0

            # Test scaled bounds
            point_data_scaled = point_data.copy()
            point_data_scaled["code"] = "TEST_YC_02"
            point_data_scaled["mul_coe"] = 0.1
            point_data_scaled["add_coe"] = 50.0
            res_yc2 = PointDao.create_yc(channel_id, point_data_scaled)
            print(f"Yc max/min (0x21, 0.1, 50.0): {res_yc2['max_limit']} / {res_yc2['min_limit']}")
            assert res_yc2["max_limit"] == 32767 * 0.1 + 50.0
            assert res_yc2["min_limit"] == -32768 * 0.1 + 50.0

            # Test inverted bounds
            point_data_inv = point_data.copy()
            point_data_inv["code"] = "TEST_YC_03"
            point_data_inv["mul_coe"] = -1.0
            res_yc3 = PointDao.create_yc(channel_id, point_data_inv)
            print(f"Yc max/min (0x21, -1.0, 0.0): {res_yc3['max_limit']} / {res_yc3['min_limit']}")
            assert res_yc3["max_limit"] == 32768.0  # -(-32768)
            assert res_yc3["min_limit"] == -32767.0  # -(32767)

            # Clean up test data
            session.rollback()  # Rollback the channel creation handles cleanup

        print("Test passed successfully!")
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_limits_calculation()
