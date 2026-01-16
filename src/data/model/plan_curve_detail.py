from sqlalchemy import Column, Integer, Time, Float, String

from src.data.model.base import Base


# 曲线详情 数据表
class PlanCurveDetail(Base):
    __tablename__ = 'plan_curve_detail'

    id = Column(Integer, primary_key=True, comment='id')
    curve_id = Column(Integer, comment='曲线id')
    device_name = Column(String(32), comment='设备名称')
    code = Column(String(32), comment='测点编码')
    start_time = Column(Time, comment='开始时间')
    end_time = Column(Time, comment='结束时间')
    power = Column(Float, server_default='0', comment='功率')

    __table_args__ = ({'comment': '曲线详情数据表'})
