import json
from unittest.mock import patch

from src.data.service.point_mapping_service import PointMappingService


def test_clone_for_device_rewrites_self_sources_and_keeps_cross_device_sources():
    mappings = [
        {
            "id": 1,
            "device_name": "SOURCE",
            "target_point_code": "TOTAL",
            "source_point_codes": json.dumps(
                [
                    {"device_name": "SOURCE", "point_code": "P1", "alias": "self"},
                    {"device_name": "OTHER", "point_code": "P2", "alias": "external"},
                ]
            ),
            "formula": "self + external",
            "enable": True,
        },
        {
            "id": 2,
            "device_name": "OTHER",
            "target_point_code": "IGNORED",
            "source_point_codes": "[]",
            "formula": "0",
            "enable": True,
        },
    ]

    with (
        patch.object(PointMappingService, "get_all_mappings", return_value=mappings),
        patch.object(PointMappingService, "create_mapping", return_value={"id": 3}) as create_mapping,
    ):
        copied_count = PointMappingService.clone_for_device("SOURCE", "TARGET")

    assert copied_count == 1
    assert create_mapping.call_args.kwargs == {
        "device_name": "TARGET",
        "target_point_code": "TOTAL",
        "source_point_codes": [
            {"device_name": "TARGET", "point_code": "P1", "alias": "self"},
            {"device_name": "OTHER", "point_code": "P2", "alias": "external"},
        ],
        "formula": "self + external",
        "enable": True,
    }
