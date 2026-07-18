"""Regression tests for cross-protocol point/model contamination."""

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.data.service.point_protocol_filter import reject_foreign_protocol_points
from src.enums.modbus_def import ProtocolType
from src.web.api.channel.import_points import import_icd, import_points
from src.web.api.channel.protocol_guards import require_iec61850_channel, require_tabular_point_channel
from src.web.api.channel.router import update_channel
from src.web.api.exceptions import ConflictError, ValidationError
from src.web.api.schemas.channel import ChannelUpdateRequest


class ProtocolGuardTests(unittest.TestCase):
    def test_icd_import_rejects_iec104_channel_before_reading_file(self):
        channel = {"id": 2, "name": "PCS2", "protocol_type": 2}
        file = SimpleNamespace(filename="KG_BAMS.icd")

        with patch(
            "src.web.api.channel.protocol_guards.ChannelService.get_channel_by_id",
            return_value=channel,
        ):
            with self.assertRaisesRegex(ValidationError, "不是 IEC 61850"):
                asyncio.run(import_icd(SimpleNamespace(), channel_id=2, file=file))

    def test_excel_import_rejects_iec61850_channel_before_reading_file(self):
        channel = {"id": 3, "name": "IEC61850SERVER", "protocol_type": 4}
        file = SimpleNamespace(filename="points.xlsx")

        with patch(
            "src.web.api.channel.protocol_guards.ChannelService.get_channel_by_id",
            return_value=channel,
        ):
            with self.assertRaisesRegex(ValidationError, "请使用 ICD/SCL"):
                asyncio.run(import_points(SimpleNamespace(), channel_id=3, file=file))

    def test_protocol_change_with_existing_points_is_rejected(self):
        existing = {
            "id": 3,
            "name": "IEC61850SERVER",
            "protocol_type": 4,
            "conn_type": 2,
            "icd_path": None,
            "model_name": None,
        }
        req = ChannelUpdateRequest(channel_id=3, protocol_type=2, conn_type=1)

        with (
            patch(
                "src.web.api.channel.router.ChannelService.get_channel_by_id",
                return_value=existing,
            ),
            patch("src.web.api.channel.router.PointDao.count_points_by_channel", return_value=8),
        ):
            with self.assertRaises(ConflictError) as context:
                asyncio.run(update_channel(req, SimpleNamespace()))

        self.assertEqual(context.exception.data["point_count"], 8)

    def test_protocol_family_guards_accept_matching_channels(self):
        iec61850 = {"id": 3, "name": "S", "protocol_type": 4}
        iec104 = {"id": 2, "name": "C", "protocol_type": 2}

        with patch(
            "src.web.api.channel.protocol_guards.ChannelService.get_channel_by_id",
            side_effect=[iec61850, iec104],
        ):
            self.assertEqual(require_iec61850_channel(3), iec61850)
            self.assertEqual(require_tabular_point_channel(2), iec104)


class PointProtocolFilterTests(unittest.TestCase):
    def test_iec61850_rows_are_rejected_for_iec104(self):
        rows = [
            {"code": "mms", "reg_addr": "STCK01/GGIO1.Alm.stVal", "fc": "ST"},
            {"code": "iec104", "reg_addr": "1001", "fc": None},
        ]

        with patch("src.data.service.point_protocol_filter.log.warning") as warning:
            accepted = reject_foreign_protocol_points(rows, 2, ProtocolType.Iec104Client, "遥信")

        self.assertEqual([row["code"] for row in accepted], ["iec104"])
        warning.assert_called_once()

    def test_numeric_rows_are_rejected_for_iec61850(self):
        rows = [
            {"code": "mms", "reg_addr": "STCK01/GGIO1.Alm.stVal", "fc": None},
            {"code": "modbus", "reg_addr": "0x0001", "fc": None},
        ]

        accepted = reject_foreign_protocol_points(rows, 3, ProtocolType.Iec61850Server, "遥信")

        self.assertEqual([row["code"] for row in accepted], ["mms"])


if __name__ == "__main__":
    unittest.main()
