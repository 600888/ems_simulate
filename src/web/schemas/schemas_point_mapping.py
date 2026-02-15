from pydantic import BaseModel, Field
from typing import Optional

class SourcePointItem(BaseModel):
    device_name: str = Field(..., description="源设备名称")
    point_code: str = Field(..., description="源测点编码")
    alias: str = Field(..., description="公式中使用的别名")
