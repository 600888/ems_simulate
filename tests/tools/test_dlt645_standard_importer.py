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
