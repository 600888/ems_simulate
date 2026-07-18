import importlib


def test_point_mapping_api_can_be_imported():
    module = importlib.import_module("src.web.api.point_mapping")

    assert module is not None
