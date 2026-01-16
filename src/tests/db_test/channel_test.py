from typing import List
import unittest
from src.data.dao.channel_dao import ChannelDao
from src.data.controller.db import db_controller
from src.data.service.channel_service import ChannelService


class ChannelTest(unittest.TestCase):
    def setUp(self):
        return super().setUp()

    def test_get_channel_list(self):
        channel_list = ChannelService.get_channel_list()
        for channel in channel_list:
            print(channel)


if __name__ == "__main__":
    unittest.main()
