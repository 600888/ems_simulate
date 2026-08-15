from src.tools import dlt645_standard_importer as importer_module


class _QueryStub:
    def where(self, *_args):
        return self

    def delete(self):
        return 0


class _SessionStub:
    captured_points = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def begin(self):
        return self

    def query(self, _model):
        return _QueryStub()

    def bulk_save_objects(self, points):
        self.captured_points.extend(points)


def test_standard_importer_uses_every_library_di(monkeypatch):
    _SessionStub.captured_points = []
    monkeypatch.setattr(importer_module, "local_session", _SessionStub)

    count = importer_module.Dlt645StandardPointImporter(88).import_points()
    points = _SessionStub.captured_points

    assert count == len(points)
    assert count > 20_000
    assert len({point.code for point in points}) == count
    assert all(point.channel_id == 88 for point in points)
    assert all(len(point.name) <= 64 for point in points)


def test_standard_importer_reverses_storage_address_for_existing_loader():
    assert importer_module._storage_address(0x01010200) == "0x00020101"


class _Item:
    def __init__(self, name="item", min_value=None, max_value=None):
        self.name = name
        self.min_value = min_value
        self.max_value = max_value


def test_item_limits_reads_range_from_library_item():
    item = _Item(name="电能量", min_value=-799999.99, max_value=799999.99)
    assert importer_module._item_limits(item) == (-799999.99, 799999.99)


def test_item_limits_falls_back_to_decode_defaults_when_unlimited(monkeypatch):
    monkeypatch.setattr(
        importer_module.Decode,
        "get_limits_by_code",
        classmethod(lambda cls, *args: (9999.0, -9999.0)),
    )
    item = _Item(name="无范围", min_value=None, max_value=None)
    assert importer_module._item_limits(item) == (-9999.0, 9999.0)


def test_item_limits_unions_list_children():
    item = [
        _Item(name="a", min_value=-5.0, max_value=100.0),
        _Item(name="b", min_value=-20.0, max_value=50.0),
        _Item(name="c", min_value=None, max_value=200.0),
    ]
    assert importer_module._item_limits(item) == (-20.0, 200.0)


def test_standard_importer_uses_library_value_ranges(monkeypatch):
    _SessionStub.captured_points = []
    monkeypatch.setattr(importer_module, "local_session", _SessionStub)

    importer_module.Dlt645StandardPointImporter(88).import_points()
    points = {point.code: point for point in _SessionStub.captured_points}

    # 电能量 DI 0x00000000：库中范围 ±799999.99
    energy = points.get("0x00000000")
    assert energy is not None
    assert energy.max_limit == 799999.99
    assert energy.min_limit == -799999.99

    # 库中未定义范围的数据项应回退到解码码默认边界，而不是沿用默认 0x41 值
    from dlt645.model.data.define import DIMap  # noqa: F401

    unlimited = [
        code for code, point in points.items() if point.max_limit == 2147483647.0 or point.min_limit == -2147483648.0
    ]
    assert unlimited, "应存在回退到默认边界的点"
