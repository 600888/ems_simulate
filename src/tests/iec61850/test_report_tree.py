import unittest

from src.proto.iec61850.plugins.reports.report_tree import (
    ReportTreeBuilder,
    decode_quality,
    decode_timestamp,
    parse_report_ref,
    parse_structured_value,
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

    def test_parse_dollar_ref_at_do_level(self):
        parsed = parse_report_ref("PCS001MEAS/dcGGIO1$MX$AnIn1")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.do_ref, "PCS001MEAS/dcGGIO1.AnIn1")
        self.assertEqual(parsed.da_parts, ())

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

    def test_serialized_analogue_structure_expands_to_mag_quality_timestamp(self):
        entry = {
            "data_values": {
                "LD0/MMXU1$MX$Temp1$mag$f": "[[43.0], 0.0, 0.0]",
            },
            "reason_codes": {"LD0/MMXU1$MX$Temp1$mag$f": "gi"},
        }

        tree = ReportTreeBuilder().build(entry)
        do_node = tree[0]["children"][0]["children"][0]
        children = {child["label"]: child for child in do_node["children"]}

        self.assertEqual(set(children), {"mag", "q", "t"})
        self.assertEqual(children["mag"]["children"][0]["label"], "f")
        self.assertEqual(children["mag"]["children"][0]["value"], 43.0)
        self.assertEqual(children["q"]["value"], "good")
        self.assertTrue(children["q"]["children"])
        self.assertEqual(children["t"]["value"], decode_timestamp(0)["datetime"])

    def test_status_structure_expands_to_stval_quality_timestamp(self):
        entry = {
            "data_values": {"LD0/GGIO1.Ind1": "[true, 0, 1000]"},
            "reason_codes": {"LD0/GGIO1.Ind1": "data-change"},
        }

        tree = ReportTreeBuilder().build(entry)
        do_node = tree[0]["children"][0]["children"][0]
        children = {child["label"]: child for child in do_node["children"]}

        self.assertIs(children["stVal"]["value"], True)
        self.assertEqual(children["q"]["value"], "good")
        self.assertEqual(children["t"]["children"][0]["label"], "Datetime")

    def test_integer_status_structure_is_expanded(self):
        entry = {"data_values": {"LD0/GGIO1.Ind1": [1, 0, 1000]}}

        tree = ReportTreeBuilder().build(entry)
        do_node = tree[0]["children"][0]["children"][0]

        self.assertEqual(do_node["children"][0]["label"], "stVal")
        self.assertEqual(do_node["children"][0]["value"], 1)

    def test_non_structure_array_remains_a_plain_value(self):
        entry = {"data_values": {"LD0/GGIO1.Ind1": "[1, 2]"}}

        tree = ReportTreeBuilder().build(entry)
        do_node = tree[0]["children"][0]["children"][0]

        self.assertEqual(do_node["value"], "[1, 2]")

    def test_parse_structured_value_rejects_non_literal_text(self):
        text = "__import__('os').system('echo unsafe')"

        self.assertEqual(parse_structured_value(text), text)


class ReportTreeEntrySelectionTest(unittest.TestCase):
    def test_select_latest_entry(self):
        data = [
            {"seq_num": 1, "received_at": "2026-01-01 00:00:00.000", "data_values": {}},
            {"seq_num": 2, "received_at": "2026-01-01 00:00:01.000", "data_values": {}},
        ]

        entry, summary = select_report_entry(data, None, True)

        self.assertEqual(entry["seq_num"], 2)
        self.assertEqual(summary["index"], 1)

    def test_missing_entry_key_returns_none(self):
        entry, summary = select_report_entry([{"seq_num": 1, "data_values": {}}], "missing", True)
        self.assertIsNone(entry)
        self.assertIsNone(summary)

    def test_empty_cache_returns_none(self):
        entry, summary = select_report_entry([], None, True)

        self.assertIsNone(entry)
        self.assertIsNone(summary)


if __name__ == "__main__":
    unittest.main()
