import unittest

from src.enums.point_data import Yc


class BlinkerTest(unittest.TestCase):
    def setUp(self):
        self.yc1 = Yc("1", "0x01", "03", "yc1", "yc1", 0, 0, 0, 0, 0, 1)

        self.yc2 = Yc("1", "0x02", "03", "yc2", "yc2", 1, 0, 0, 0, 0, 1)

    def on_yc_value_changed(self, sender, **extra) -> None:
        old_point: Yc = extra.get("old_point")
        related_point: Yc = extra.get("related_point")
        new_value = extra.get("new_value")
        related_point.value = new_value
        print(
            f"yc1 value changed, old_point: {old_point.value}, related_point: {related_point.value}, new_value: {new_value}"
        )

    def test_set_yc(self):
        self.yc1.is_send_signal = True
        self.yc1.related_yc = self.yc2
        self.yc1.value_changed.connect(self.on_yc_value_changed)
        self.yc1.value = 100
        print(self.yc2.value)
