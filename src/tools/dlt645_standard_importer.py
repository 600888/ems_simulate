"""Build the built-in DL/T 645-2007 point table from the dlt645 package."""

from collections.abc import Iterable

from src.data.controller.db import local_session
from src.data.model.point_yc import PointYc
from src.data.model.point_yk import PointYk
from src.data.model.point_yt import PointYt
from src.data.model.point_yx import PointYx
from src.enums.modbus_register import Decode


def _storage_address(di: int) -> str:
    """Return the byte-reversed address expected by the existing DLT645 loader."""
    raw = f"{di:08X}"
    return "0x" + "".join(raw[index : index + 2] for index in range(6, -1, -2))


def _item_name(item: object) -> str:
    if isinstance(item, list):
        names: Iterable[str] = (str(getattr(child, "name", "")) for child in item)
        name = " / ".join(value for value in names if value)
    else:
        name = str(getattr(item, "name", ""))
    # The current point schema limits names to 64 characters.
    return name[:64]


def _item_limits(item: object) -> tuple[float, float]:
    """Read the value range from the dlt645 library item (min, max).

    The library defines ``min_value``/``max_value`` per data item; ``None``
    means unlimited. For list items the union of all children is used.
    Falls back to the decode-code default limits when the library does not
    define a range.
    """
    if isinstance(item, list):
        mins = [getattr(child, "min_value", None) for child in item]
        maxs = [getattr(child, "max_value", None) for child in item]
        defined_mins = [value for value in mins if value is not None]
        defined_maxs = [value for value in maxs if value is not None]
        min_limit = min(defined_mins) if defined_mins else None
        max_limit = max(defined_maxs) if defined_maxs else None
    else:
        min_limit = getattr(item, "min_value", None)
        max_limit = getattr(item, "max_value", None)

    if min_limit is None or max_limit is None:
        default_max, default_min = Decode.get_limits_by_code("0x41", 1.0, 0.0)
        if min_limit is None:
            min_limit = default_min
        if max_limit is None:
            max_limit = default_max
    return min_limit, max_limit


class Dlt645StandardPointImporter:
    """Import every DI defined by the pinned dlt645 library as a YC point."""

    def __init__(self, channel_id: int):
        self.channel_id = channel_id

    def import_points(self) -> int:
        # Importing dlt645 initializes the package's complete DIMap.
        import dlt645  # noqa: F401
        from dlt645.model.data.define import DIMap

        points = []
        for di, item in sorted(DIMap.items()):
            min_limit, max_limit = _item_limits(item)
            points.append(
                PointYc(
                    channel_id=self.channel_id,
                    code=f"0x{di:08X}",
                    name=_item_name(item) or f"数据标识 0x{di:08X}",
                    rtu_addr=1,
                    reg_addr=_storage_address(di),
                    func_code=3,
                    decode_code="0x41",
                    mul_coe=1.0,
                    add_coe=0.0,
                    max_limit=max_limit,
                    min_limit=min_limit,
                    enable=True,
                )
            )

        with local_session() as session, session.begin():
            for model in (PointYc, PointYx, PointYk, PointYt):
                session.query(model).where(model.channel_id == self.channel_id).delete()
            session.bulk_save_objects(points)
        return len(points)
