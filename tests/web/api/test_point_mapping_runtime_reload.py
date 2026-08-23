"""测点映射保存后的运行时刷新回归测试。"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.web.api.point.mapping import PointMappingCreateRequest, create_mapping


@pytest.mark.asyncio
async def test_create_mapping_reloads_device_from_current_application_controller():
    device = SimpleNamespace(reload_mappings=Mock())
    controller = SimpleNamespace(device_map={"device-a": device})
    http_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))
    body = PointMappingCreateRequest(
        device_name="device-a",
        target_point_code="NEW_TARGET",
        source_point_codes=[{"device_name": "device-a", "point_code": "SOURCE", "alias": "source"}],
        formula="source * 2",
        enable=True,
    )

    with patch(
        "src.web.api.point.mapping.PointMappingService.create_mapping",
        return_value={"id": 9},
    ):
        response = await create_mapping(body, http_request)

    assert response.data == {"id": 9}
    device.reload_mappings.assert_called_once_with()
