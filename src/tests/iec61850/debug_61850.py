"""Debug script for IEC 61850 point loading"""

from src.data.controller.db import local_session
from src.data.model.point_yc import PointYc
from src.data.model.point_yk import PointYk
from src.data.model.point_yt import PointYt
from src.data.model.point_yx import PointYx
from src.data.service.channel_service import ChannelService

# 列出所有通道
channels = ChannelService.get_all_channels()
for ch in channels:
    cid = ch["id"]
    name = ch["name"]
    proto = ch.get("protocol_type")
    conn = ch.get("conn_type")
    print(f"Channel: id={cid}, name={name}, protocol={proto}, conn_type={conn}")

# 查看每个通道下的测点
with local_session() as session:
    for ch in channels:
        cid = ch["id"]
        yc_count = session.query(PointYc).where(PointYc.channel_id == cid).count()
        yx_count = session.query(PointYx).where(PointYx.channel_id == cid).count()
        yk_count = session.query(PointYk).where(PointYk.channel_id == cid).count()
        yt_count = session.query(PointYt).where(PointYt.channel_id == cid).count()
        total = yc_count + yx_count + yk_count + yt_count
        if total > 0:
            print(f"  Channel {cid} ({ch['name']}): yc={yc_count}, yx={yx_count}, yk={yk_count}, yt={yt_count}")
            for model, ft in [(PointYc, "yc"), (PointYx, "yx"), (PointYk, "yk"), (PointYt, "yt")]:
                pts = session.query(model).where(model.channel_id == cid).limit(5).all()
                for p in pts:
                    print(f"    {ft}: code={p.code}, reg_addr={p.reg_addr}, enable={p.enable}")
        else:
            print(f"  Channel {cid} ({ch['name']}): NO POINTS")
