from typing import Type

from sqlalchemy.orm import Session

from src.data.model.plan_curve_detail import PlanCurveDetail


class PlanCurveDao:
    def __init__(self, db_config) -> None:
        self.db_config = db_config

    # 获取某个设备某个测点的曲线信息
    def get_curve_info(self, device_name, code) -> list[Type[PlanCurveDetail]]:
        with Session(self.db_config.engine) as session, session.begin():
            try:
                plan_curve_detail_list = session.query(PlanCurveDetail).filter(
                    PlanCurveDetail.device_name == device_name,
                    PlanCurveDetail.code == code).all()
                return plan_curve_detail_list
            except Exception as e:
                self.db_config.rollback_session()
                raise e
