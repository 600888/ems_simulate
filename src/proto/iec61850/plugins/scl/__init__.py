"""SCL 离线解析模块

解析 IEC 61850 ICD/SCD/CID 文件，替代 IcdPointImporter / IcdGooseImporter。

模块结构:
  model/         — SCL 对象模型 (dataclass)
  parser/        — XML 解析引擎
  validator/     — 校验引擎
  transformer/   — 模型转换器 (SclDocument → 测点/GOOSE/Report 数据)
"""
