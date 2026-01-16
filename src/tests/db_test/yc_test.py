from typing import List
import unittest
from src.data.service.yc_service import YcService


class YcTest(unittest.TestCase):
    def setUp(self):
        return super().setUp()

    def test_get_channel_list(self):
        yc_list = YcService.get_yc_list(grp_code="PCS1")
        for item in yc_list:
            print(item.rtu_addr, item.code, item.name)


if __name__ == "__main__":
    unittest.main()
