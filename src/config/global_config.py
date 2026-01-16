import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 根目录
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../.."))
# 日志目录
LOG_DIR = os.path.join(ROOT_DIR, "log")

# 配置文件目录
CSV_DIR = os.path.join(ROOT_DIR, "config", "point_csv")
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
