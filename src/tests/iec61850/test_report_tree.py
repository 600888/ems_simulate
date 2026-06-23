import unittest

from src.proto.iec61850.plugins.reports.report_tree import (
    ReportEntryNotFoundError,
    ReportTreeBuilder,
    decode_quality,
    decode_timestamp,
    parse_report_ref,
    select_report_entry,
)


class ReportTreeBuilderTest(unittest.TestCase):
    def test_parse_dot_ref(self):
        parsed = parse_report_ref("LD0/GGIO1.Ind1.stVal")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.ld, "LD0")
        self.assertEqual(parsed.ln, "GGIO1")
        self.assertEqual(parsed.do_name, "Ind1")
        self.assertEqual(parsed.da_parts, ("stVal",))

    def test_parse_dollar_ref_with_fc(self):
        parsed = parse_report_ref("LD0/GGIO1$ST$Ind1$q")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.fc, "ST")
        self.assertEqual(parsed.do_ref, "LD0/GGIO1.Ind1")
        self.assertEqual(parsed.da_parts, ("q",))

    def test_unmapped_data_i_fallback(self):
        entry = {
            "data_values": {"data[0]": True},
            "reason_codes": {"data[0]": "gi"},
        }

        tree = ReportTreeBuilder().build(entry)

        self.assertEqual(tree[0]["label"], "Unmapped Data")
        self.assertEqual(tree[0]["children"][0]["label"], "data[0]")
        self.assertTrue(tree[0]["children"][0]["value"])

    def test_quality_decoding(self):
        # validity=good, detailQuality failure bit set, source=process, test/operatorBlocked=false
        decoded = decode_quality(1 << 6)

        self.assertEqual(decoded["validity_text"], "good")
        self.assertTrue(decoded["failure"])
        self.assertFalse(decoded["operator_blocked"])

    def test_timestamp_decoding(self):
        decoded = decode_timestamp(1000)

        self.assertEqual(decoded["seconds"], 1)
        self.assertEqual(decoded["unix_ms"], 1000)

    def test_same_do_merges_stval_quality_and_timestamp(self):
        entry = {
            "data_values": {
                "LD0/GGIO1.Ind1.stVal": True,
                "LD0/GGIO1.Ind1.q": 0,
                "LD0/GGIO1.Ind1.t": 1000,
            },
            "reason_codes": {
                "LD0/GGIO1.Ind1.stVal": "gi",
                "LD0/GGIO1.Ind1.q": "gi",
                "LD0/GGIO1.Ind1.t": "gi",
            },
        }

        tree = ReportTreeBuilder().build(entry)
        do_node = tree[0]["children"][0]["children"][0]
        child_labels = [child["label"] for child in do_node["children"]]

        self.assertEqual(do_node["label"], "Ind1")
        self.assertIn("stVal", child_labels)
        self.assertIn("q", child_labels)
        self.assertIn("t", child_labels)


class ReportTreeEntrySelectionTest(unittest.TestCase):
    def test_select_latest_entry(self):
        data = [
            {"seq_num": 1, "received_at": "2026-01-01 00:00:00.000", "data_values": {}},
            {"seq_num": 2, "received_at": "2026-01-01 00:00:01.000", "data_values": {}},
        ]

        entry, summary = select_report_entry(data, None, True)

        self.assertEqual(entry["seq_num"], 2)
        self.assertEqual(summary["index"], 1)

    def test_missing_entry_key_raises_not_found(self):
        with self.assertRaises(ReportEntryNotFoundError):
            select_report_entry([{"seq_num": 1, "data_values": {}}], "missing", True)

    def test_empty_cache_returns_none(self):
        entry, summary = select_report_entry([], None, True)

        self.assertIsNone(entry)
        self.assertIsNone(summary)


if __name__ == "__main__":
    unittest.main()
