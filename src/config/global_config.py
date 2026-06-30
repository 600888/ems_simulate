import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 根目录（支持 EMS_ROOT_DIR 环境变量覆盖，用于 MSIX/Sidecar 模式持久化数据）
EMS_ROOT_DIR = os.environ.get("EMS_ROOT_DIR")
if EMS_ROOT_DIR:
    ROOT_DIR = EMS_ROOT_DIR
elif getattr(sys, "frozen", False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../.."))
# 日志目录
LOG_DIR = os.path.join(ROOT_DIR, "log")

# 配置文件目录
CSV_DIR = os.path.join(ROOT_DIR, "data", "point_csv")
CONFIG_DIR = os.path.join(ROOT_DIR, "config")
CONFIG_JSON_DIR = os.path.join(ROOT_DIR, "config", "device_config")
TEMPLATE_DIR = os.path.join(CONFIG_DIR, "template")
# 模拟计划目录
PLAN_JSON_DIR = os.path.join(ROOT_DIR, "plan")
PCS_PLAN_DIR = os.path.join(PLAN_JSON_DIR, "pcs")
BMS_PLAN_DIR = os.path.join(PLAN_JSON_DIR, "bms")
METER_PLAN_DIR = os.path.join(PLAN_JSON_DIR, "meter")
# 上传文件目录
UPLOAD_DIR = os.path.join(ROOT_DIR, "upload")
UPLOAD_PLAN_DIR = os.path.join(UPLOAD_DIR, "plan")
# 前端界面目录
VIEW_DIR = os.path.join(ROOT_DIR, "src", "views")
