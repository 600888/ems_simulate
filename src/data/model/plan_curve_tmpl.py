from sqlalchemy import Column, Integer, String

from src.data.model.base import Base


# 曲线模板 数据表
class PlanCurveTmpl(Base):
    __tablename__ = 'plan_curve_tmpl'

    id = Column(Integer, primary_key=True, comment='id')
    curve_id = Column(Integer, comment='曲线模板id')
    name = Column(String(32), unique=True, comment='曲线模板名称')

    __table_args__ = ({'comment': '曲线模板表'})
