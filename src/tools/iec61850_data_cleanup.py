"""
IEC 61850 数据清理脚本

整改第三阶段: 彻底删除数据库中所有与 61850 测点相关的冗余存储记录。

清理目标:
  - point_yc 表中 protocol_type=4 (IEC61850) 或通道协议为 IEC61850 的测点记录
  - point_yx 表中同上条件的测点记录
  - point_yk 表中同上条件的测点记录
  - point_yt 表中同上条件的测点记录

安全措施:
  1. 清理前自动备份到 JSON 文件
  2. 支持 dry_run 模式（仅统计，不执行删除）
  3. 日志记录所有操作
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from src.data.controller.db import local_session
from src.data.log import log
from src.data.model.channel import Channel
from src.data.model.point_yc import PointYc
from src.data.model.point_yk import PointYk
from src.data.model.point_yt import PointYt
from src.data.model.point_yx import PointYx

# IEC61850 的 protocol_type 值 (channel 表中 conn_type=2 且 protocol_type=4)
IEC61850_PROTOCOL_TYPE = 4
IEC61850_CONN_TYPES = (1, 2)  # TCP 客户端或服务端


def get_iec61850_channel_ids(session) -> set[int]:
    """获取所有 IEC61850 协议的通道 ID"""
    channels = (
        session.query(Channel.id)
        .filter(
            Channel.protocol_type == IEC61850_PROTOCOL_TYPE,
            Channel.conn_type.in_(IEC61850_CONN_TYPES),
        )
        .all()
    )
    return {c[0] for c in channels}


def count_iec61850_points(session, channel_ids: set[int]) -> dict[str, int]:
    """统计所有 IEC61850 协议的测点数量（按表分组）"""
    if not channel_ids:
        return {"yc": 0, "yx": 0, "yk": 0, "yt": 0}

    yc_count = session.query(PointYc).filter(PointYc.channel_id.in_(channel_ids)).count()
    yx_count = session.query(PointYx).filter(PointYx.channel_id.in_(channel_ids)).count()
    yk_count = session.query(PointYk).filter(PointYk.channel_id.in_(channel_ids)).count()
    yt_count = session.query(PointYt).filter(PointYt.channel_id.in_(channel_ids)).count()

    return {"yc": yc_count, "yx": yx_count, "yk": yk_count, "yt": yt_count}


def backup_iec61850_points(session, channel_ids: set[int], backup_dir: str = "data/backup") -> str:
    """备份即将删除的 IEC61850 测点数据到 JSON 文件

    Returns:
        备份文件路径
    """
    if not channel_ids:
        return ""

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"iec61850_points_backup_{timestamp}.json"

    backup_data = {
        "backup_time": timestamp,
        "description": "IEC61850 测点数据清理备份 (整改计划第三阶段)",
        "channel_ids": list(channel_ids),
        "tables": {
            "point_yc": [],
            "point_yx": [],
            "point_yk": [],
            "point_yt": [],
        },
    }

    # 备份各表数据
    points_yc = session.query(PointYc).filter(PointYc.channel_id.in_(channel_ids)).all()
    backup_data["tables"]["point_yc"] = [p.to_dict() for p in points_yc]

    points_yx = session.query(PointYx).filter(PointYx.channel_id.in_(channel_ids)).all()
    backup_data["tables"]["point_yx"] = [p.to_dict() for p in points_yx]

    points_yk = session.query(PointYk).filter(PointYk.channel_id.in_(channel_ids)).all()
    backup_data["tables"]["point_yk"] = [p.to_dict() for p in points_yk]

    points_yt = session.query(PointYt).filter(PointYt.channel_id.in_(channel_ids)).all()
    backup_data["tables"]["point_yt"] = [p.to_dict() for p in points_yt]

    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"IEC61850 测点数据已备份到: {backup_file}")
    return str(backup_file)


def delete_iec61850_points(session, channel_ids: set[int]) -> dict[str, int]:
    """删除所有 IEC61850 协议的测点记录

    Returns:
        各表的删除数量
    """
    if not channel_ids:
        return {"yc": 0, "yx": 0, "yk": 0, "yt": 0}

    yc_deleted = session.query(PointYc).filter(PointYc.channel_id.in_(channel_ids)).delete(synchronize_session=False)
    yx_deleted = session.query(PointYx).filter(PointYx.channel_id.in_(channel_ids)).delete(synchronize_session=False)
    yk_deleted = session.query(PointYk).filter(PointYk.channel_id.in_(channel_ids)).delete(synchronize_session=False)
    yt_deleted = session.query(PointYt).filter(PointYt.channel_id.in_(channel_ids)).delete(synchronize_session=False)

    return {"yc": yc_deleted, "yx": yx_deleted, "yk": yk_deleted, "yt": yt_deleted}


def verify_cleanup(session, channel_ids: set[int]) -> dict[str, int]:
    """验证清理结果: 确认相关表中已无指定通道的测点记录

    Returns:
        各表的剩余记录数（应为 0）
    """
    remaining = count_iec61850_points(session, channel_ids)
    return remaining


def run_cleanup(dry_run: bool = True) -> dict:
    """执行 IEC61850 数据清理

    Args:
        dry_run: True 时仅统计和备份，不执行删除（默认）
                 False 时执行完整清理流程

    Returns:
        操作结果字典
    """
    result = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "status": "pending",
        "channel_ids": [],
        "counts_before": {},
        "backup_file": "",
        "deleted_counts": {},
        "remaining_after": {},
        "errors": [],
    }

    try:
        with local_session() as session, session.begin():
            # 1. 获取 IEC61850 通道
            channel_ids = get_iec61850_channel_ids(session)
            result["channel_ids"] = list(channel_ids)

            if not channel_ids:
                log.info("未找到 IEC61850 通道，无需清理")
                result["status"] = "noop"
                return result

            # 2. 统计清理前的数量
            counts_before = count_iec61850_points(session, channel_ids)
            result["counts_before"] = counts_before
            total_before = sum(counts_before.values())

            log.info(f"IEC61850 数据清理开始: {len(channel_ids)} 个通道, {total_before} 个测点")
            log.info(
                f"  遥测: {counts_before['yc']}, 遥信: {counts_before['yx']}, "
                f"遥控: {counts_before['yk']}, 遥调: {counts_before['yt']}"
            )

            if total_before == 0:
                log.info("IEC61850 通道无关联测点，无需清理")
                result["status"] = "clean"
                return result

            # 3. 备份数据
            backup_file = backup_iec61850_points(session, channel_ids)
            result["backup_file"] = backup_file

            if dry_run:
                log.info("*** DRY RUN 模式: 不执行实际删除 ***")
                result["status"] = "dry_run"
                return result

            # 4. 执行删除
            deleted_counts = delete_iec61850_points(session, channel_ids)
            result["deleted_counts"] = deleted_counts
            total_deleted = sum(deleted_counts.values())

            # 5. 验证
            remaining = verify_cleanup(session, channel_ids)
            result["remaining_after"] = remaining
            total_remaining = sum(remaining.values())

            if total_remaining == 0:
                result["status"] = "success"
                log.info(f"IEC61850 数据清理完成: 已删除 {total_deleted} 条记录, 验证通过")
            else:
                result["status"] = "partial"
                log.warning(
                    f"IEC61850 数据清理部分完成: 已删除 {total_deleted} 条, "
                    f"剩余 {total_remaining} 条 (可能为其他协议数据)"
                )

    except Exception as e:
        log.error(f"IEC61850 数据清理失败: {e}", exc_info=True)
        result["status"] = "failed"
        result["errors"].append(str(e))

    return result


def run_dry_run() -> dict:
    """执行 DRY RUN: 仅统计和备份，不执行删除"""
    return run_cleanup(dry_run=True)


def run_full_cleanup() -> dict:
    """执行完整清理: 备份 + 删除 + 验证"""
    return run_cleanup(dry_run=False)


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "dry-run"

    if mode == "dry-run":
        print("=== IEC61850 数据清理 DRY RUN 模式 ===")
        result = run_dry_run()
    elif mode == "exec":
        print("=== IEC61850 数据清理 EXEC 模式 ===")
        confirm = input("确认要执行 IEC61850 数据清理吗? (yes/no): ")
        if confirm.lower() == "yes":
            result = run_full_cleanup()
        else:
            print("已取消")
            exit(0)
    else:
        print(f"用法: python {sys.argv[0]} [dry-run|exec]")
        exit(1)

    print(f"\n结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
