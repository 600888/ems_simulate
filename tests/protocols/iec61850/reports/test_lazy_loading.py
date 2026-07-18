import asyncio
import unittest
from unittest.mock import patch

from src.proto.iec61850.defs.types import ReportDataEntry
from src.proto.iec61850.plugins.reports import callback
from src.web.api.channel import report as report_api
from src.web.api.schemas.report import ReportDataRequest, ReportTreeDataRequest


class ReportCacheLazyLoadingTest(unittest.TestCase):
    def setUp(self):
        self.rcb_ref = "LD0/LLN0.rp01"
        self.info = callback._CallbackInfo(rcb_ref=self.rcb_ref)
        callback._CALLBACK_REGISTRY[self.rcb_ref] = self.info

    def tearDown(self):
        callback._CALLBACK_REGISTRY.pop(self.rcb_ref, None)

    def test_history_summaries_do_not_include_report_values(self):
        self.info.data_cache.extend(
            [
                ReportDataEntry(uid=41, seq_num=1, data_values={"LD0/GGIO1.Ind1": True}),
                ReportDataEntry(uid=42, seq_num=2, data_values={"LD0/GGIO1.Ind2": False}),
            ]
        )

        summaries = callback.ReportCallbackHandler.get_cache_summaries(self.rcb_ref, limit=1)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["entry_key"], "uid:42")
        self.assertEqual(summaries[0]["value_count"], 1)
        self.assertNotIn("data_values", summaries[0])

    def test_single_entry_is_selected_by_uid(self):
        self.info.data_cache.extend(
            [
                ReportDataEntry(uid=41, seq_num=1),
                ReportDataEntry(uid=42, seq_num=2),
            ]
        )

        entry = callback.ReportCallbackHandler.get_cache_entry(self.rcb_ref, uid=41)

        self.assertEqual(entry["uid"], 41)
        self.assertEqual(entry["seq_num"], 1)


class ReportLazyApiTest(unittest.TestCase):
    def test_state_endpoint_does_not_load_report_values(self):
        class FakeReports:
            @staticmethod
            def get_report_data_state(_rcb_ref):
                return 7, 42

            @staticmethod
            def get_report_data(*_args, **_kwargs):
                raise AssertionError("state endpoint must not serialize report values")

        body = ReportTreeDataRequest(channel_id=1, rcb_ref="LD0/LLN0.rp01")
        with patch.object(report_api, "_get_reports_plugin", return_value=FakeReports()):
            response = asyncio.run(report_api.get_report_state(body, object()))

        self.assertEqual(response.data, {"total": 7, "latest_uid": 42})

    def test_history_endpoint_returns_summaries_only(self):
        class FakeReports:
            @staticmethod
            def get_report_data_state(_rcb_ref):
                return 1, 42

            @staticmethod
            def get_report_summaries(_rcb_ref, _limit):
                return [{"entry_key": "uid:42", "value_count": 1}]

        body = ReportDataRequest(channel_id=1, rcb_ref="LD0/LLN0.rp01")
        with patch.object(report_api, "_get_reports_plugin", return_value=FakeReports()):
            response = asyncio.run(report_api.get_report_history(body, object()))

        self.assertEqual(response.data["entries"], [{"entry_key": "uid:42", "value_count": 1}])
        self.assertNotIn("data_values", response.data["entries"][0])

    def test_latest_endpoint_loads_only_the_latest_entry(self):
        class FakeReports:
            @staticmethod
            def get_report_data_state(_rcb_ref):
                return 8, 42

            @staticmethod
            def get_report_entry(rcb_ref, *, latest):
                self.assertEqual(rcb_ref, "LD0/LLN0.rp01")
                self.assertTrue(latest)
                return {
                    "uid": 42,
                    "seq_num": 8,
                    "data_values": {"LD0/GGIO1.Ind1.stVal": True},
                    "reason_codes": {"LD0/GGIO1.Ind1.stVal": "data-change"},
                }

        body = ReportTreeDataRequest(channel_id=1, rcb_ref="LD0/LLN0.rp01")
        with patch.object(report_api, "_get_reports_plugin", return_value=FakeReports()):
            response = asyncio.run(report_api.get_latest_report(body, object()))

        self.assertEqual(response.data["latest_uid"], 42)
        self.assertEqual(response.data["entry"]["entry_key"], "uid:42")
        self.assertTrue(response.data["tree_items"])

    def test_tree_endpoint_requests_only_selected_uid(self):
        requested_uids = []

        class FakeReports:
            @staticmethod
            def get_report_entry(rcb_ref, *, uid, latest):
                self.assertEqual(rcb_ref, "LD0/LLN0.rp01")
                requested_uids.append((uid, latest))
                return {"uid": uid, "seq_num": 7, "data_values": {}, "reason_codes": {}}

        body = ReportTreeDataRequest(
            channel_id=1,
            rcb_ref="LD0/LLN0.rp01",
            entry_key="uid:42",
            latest=False,
        )
        with patch.object(report_api, "_get_reports_plugin", return_value=FakeReports()):
            response = asyncio.run(report_api.get_report_data_tree(body, object()))

        self.assertEqual(requested_uids, [(42, False)])
        self.assertEqual(response.data["entry"]["entry_key"], "uid:42")


if __name__ == "__main__":
    unittest.main()
