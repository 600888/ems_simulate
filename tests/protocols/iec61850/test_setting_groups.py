from types import SimpleNamespace

from src.proto.iec61850.plugins.setting_groups import SettingGroupsPlugin


class _FakeClient:
    def __init__(self):
        self.model = SimpleNamespace(
            point_refs={
                "LD0/PTOC1.StrVal.setMag.f": {
                    "ref": "IEDLD0/PTOC1.StrVal.setMag.f",
                    "fc": "SG",
                    "iec_type": "float",
                    "mms_type": "MMS_FLOAT",
                },
                "LD1/PTOC1.StrVal.setMag.f": {
                    "ref": "IEDLD1/PTOC1.StrVal.setMag.f",
                    "fc": "SG",
                },
                "LD0/MMXU1.A.phsA.cVal.mag.f": {
                    "ref": "IEDLD0/MMXU1.A.phsA.cVal.mag.f",
                    "fc": "MX",
                },
            }
        )
        self.read_calls = []
        self.write_calls = []

    def read_point(self, address, fc=""):
        self.read_calls.append((address, fc))
        return 10 if fc == "SG" else 12

    def write_point(self, address, value, fc=""):
        self.write_calls.append((address, value, fc))
        return True


def test_list_settings_uses_entire_logical_device_not_only_lln0():
    plugin = SettingGroupsPlugin()
    plugin._client = _FakeClient()

    settings = plugin.list_settings("IEDLD0/LLN0.SGCB")

    assert [item["ref"] for item in settings] == ["IEDLD0/PTOC1.StrVal.setMag.f"]
    assert settings[0]["current_value"] == 10
    assert settings[0]["edit_value"] == 12
    assert plugin._client.read_calls == [
        ("LD0/PTOC1.StrVal.setMag.f", "SG"),
        ("LD0/PTOC1.StrVal.setMag.f", "SE"),
    ]


def test_write_values_always_targets_edit_fc():
    plugin = SettingGroupsPlugin()
    plugin._client = _FakeClient()

    result = plugin.write_values([{"address": "LD0/PTOC1.StrVal.setMag.f", "value": "12.5"}])

    assert result == [{"address": "LD0/PTOC1.StrVal.setMag.f", "success": True}]
    assert plugin._client.write_calls == [("LD0/PTOC1.StrVal.setMag.f", "12.5", "SE")]
