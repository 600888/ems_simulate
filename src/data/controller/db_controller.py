"""
数据库控制器
支持 SQLite 和 MySQL 数据库的初始化和管理
"""

from pathlib import Path

from src.config.db.db_config import DbMysqlConfig, DbSqliteConfig
from src.data.model.base import Base


class DbController:
    """数据库控制器，统一管理数据库连接"""

    def __init__(self) -> None:
        self.db_config: DbMysqlConfig | DbSqliteConfig | None = None
        self._db_type: str = "sqlite"

    @property
    def engine(self):
        """获取数据库引擎"""
        if self.db_config:
            return self.db_config.engine
        return None

    def close_db(self) -> None:
        """关闭数据库连接"""
        if self.db_config:
            self.db_config.close_engine()

    def init_db(self, db_type: str, **kwargs) -> bool:
        """根据类型初始化数据库

        Args:
            db_type: 数据库类型 (sqlite/mysql)
            **kwargs: 数据库配置参数

        Returns:
            bool: 初始化是否成功
        """
        self._db_type = db_type.lower()

        if self._db_type == "sqlite":
            return self.init_sqlite_db(db_path=kwargs.get("db_path", "data/ems.db"))
        else:
            return self.init_mysql_db(
                ip=kwargs.get("ip", "127.0.0.1"),
                port=kwargs.get("port", "3306"),
                user_name=kwargs.get("user_name", "root"),
                pass_word=kwargs.get("pass_word", ""),
                database=kwargs.get("database", "ems_simulate"),
            )

    def init_sqlite_db(self, db_path: str) -> bool:
        """初始化 SQLite 数据库

        Args:
            db_path: 数据库文件路径

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 确保目录存在
            db_dir = Path(db_path).parent
            if not db_dir.exists():
                db_dir.mkdir(parents=True, exist_ok=True)

            self.db_config = DbSqliteConfig()
            self.db_config.set_db_path(db_path)
            self.db_config.create_engine()

            # 新旧 IEC 61850 建模存储结构不兼容，先按升级策略清理旧表。
            self._reset_legacy_iec61850_modeling_schema()

            # 创建所有表
            Base.metadata.create_all(self.db_config.engine)
            self._migrate_channel_point_table_mode_schema()
            self._migrate_dnp3_point_config_schema()
            self._migrate_goose_schema()
            self._migrate_channel_security_schema()

            # 迁移: 为现有数据库添加 IEC61850 相关字段
            try:
                from sqlalchemy import text

                with self.db_config.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE channel ADD COLUMN model_name VARCHAR(128)"))
                    conn.commit()
            except Exception:
                pass  # 列已存在或数据库不支持

            try:
                from sqlalchemy import text

                with self.db_config.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE channel ADD COLUMN icd_path VARCHAR(512)"))
                    conn.commit()
            except Exception:
                pass  # 列已存在或数据库不支持

            try:
                from sqlalchemy import text

                with self.db_config.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE channel ADD COLUMN icd_file_hash VARCHAR(64)"))
                    conn.commit()
            except Exception:
                pass  # 列已存在或数据库不支持

            try:
                from sqlalchemy import text

                with self.db_config.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE device ADD COLUMN icd_path VARCHAR(512)"))
                    conn.commit()
            except Exception:
                pass  # 列已存在或数据库不支持

            try:
                from sqlalchemy import text

                with self.db_config.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE device ADD COLUMN icd_file_hash VARCHAR(64)"))
                    conn.commit()
            except Exception:
                pass  # 列已存在或数据库不支持

            print(f"SQLite 数据库初始化成功: {db_path}")
            return True
        except Exception as e:
            print(f"SQLite 数据库初始化失败: {e}")
            return False

    def init_mysql_db(
        self,
        ip: str,
        port: str,
        user_name: str,
        pass_word: str,
        database: str = "net",
    ) -> bool:
        """初始化 MySQL 数据库

        Args:
            ip: MySQL 主机地址
            port: MySQL 端口
            user_name: 用户名
            pass_word: 密码
            database: 数据库名

        Returns:
            bool: 初始化是否成功
        """
        try:
            self.db_config = DbMysqlConfig()
            self.db_config.set_db_config(ip, port, user_name, pass_word)
            self.db_config.create_engine(database, is_create_db=False)
            self._reset_legacy_iec61850_modeling_schema()
            Base.metadata.create_all(self.db_config.engine)
            self._migrate_channel_point_table_mode_schema()
            self._migrate_dnp3_point_config_schema()
            self._migrate_goose_schema()
            self._migrate_channel_security_schema()

            print(f"MySQL 数据库连接成功: {ip}:{port}/{database}")
            return True
        except Exception as e:
            print(f"MySQL 数据库连接失败: {e}")
            return False

    def is_sqlite(self) -> bool:
        """是否使用 SQLite"""
        return self._db_type == "sqlite"

    def is_mysql(self) -> bool:
        """是否使用 MySQL"""
        return self._db_type == "mysql"

    def _migrate_channel_point_table_mode_schema(self) -> None:
        """Add the persisted DLT645 point-table source to existing databases.

        Legacy rows default to ``import`` because their original source cannot
        be known safely. This prevents an ordinary edit from replacing an
        existing point table with the full standard table.
        """
        if not self.db_config:
            return

        from sqlalchemy import inspect, text

        engine = self.db_config.engine
        inspector = inspect(engine)
        if "channel" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("channel")}
        if "dlt645_point_mode" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE channel ADD COLUMN dlt645_point_mode VARCHAR(16) NOT NULL DEFAULT 'import'")
                )
            self._backfill_legacy_dlt645_standard_tables()

    def _migrate_dnp3_point_config_schema(self) -> None:
        """Add one extensible JSON field to every legacy point table."""
        if not self.db_config:
            return
        from sqlalchemy import inspect, text

        engine = self.db_config.engine
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        for table in ("point_yc", "point_yx", "point_yk", "point_yt"):
            if table not in tables:
                continue
            columns = {column["name"] for column in inspector.get_columns(table)}
            if "dnp3_config" not in columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN dnp3_config TEXT"))

    def _backfill_legacy_dlt645_standard_tables(self) -> None:
        """Recognize legacy standard tables by their complete DI code set."""
        if not self.db_config:
            return

        from dlt645.model.data.define import DIMap
        from sqlalchemy import inspect, text

        engine = self.db_config.engine
        table_names = set(inspect(engine).get_table_names())
        point_tables = {"point_yc", "point_yx", "point_yk", "point_yt"}
        if not point_tables.issubset(table_names):
            return

        standard_codes = {f"0x{di:08X}" for di in DIMap}
        with engine.begin() as conn:
            channel_ids = conn.scalars(text("SELECT id FROM channel WHERE protocol_type = 3")).all()
            for channel_id in channel_ids:
                codes = set(
                    conn.scalars(
                        text("SELECT code FROM point_yc WHERE channel_id = :channel_id"),
                        {"channel_id": channel_id},
                    ).all()
                )
                if codes != standard_codes:
                    continue
                has_other_points = any(
                    conn.scalar(
                        text(f"SELECT COUNT(*) FROM {table} WHERE channel_id = :channel_id"),
                        {"channel_id": channel_id},
                    )
                    for table in ("point_yx", "point_yk", "point_yt")
                )
                if not has_other_points:
                    conn.execute(
                        text("UPDATE channel SET dlt645_point_mode = 'standard' WHERE id = :channel_id"),
                        {"channel_id": channel_id},
                    )

    def _reset_legacy_iec61850_modeling_schema(self) -> None:
        """检测并重建不兼容的旧版 IEC 61850 建模表。

        旧版模型节点分散存储在 ``iec61850_model_node`` 和
        ``iec61850_model_reference`` 中；新版将完整模型存入
        ``iec61850_model_project.model_json``。这里按产品升级策略丢弃旧建模
        数据，仅在 project 表缺少新版必需列时执行，因此可安全重复启动。
        """
        if not self.db_config:
            return

        from sqlalchemy import inspect, text

        engine = self.db_config.engine
        inspector = inspect(engine)
        project_table = "iec61850_model_project"
        if project_table not in inspector.get_table_names():
            return

        existing_columns = {column["name"] for column in inspector.get_columns(project_table)}
        required_columns = {
            "model_json",
            "model_format_version",
            "model_node_count",
            "model_checksum",
        }
        if required_columns.issubset(existing_columns):
            return

        # 先删有外键依赖的子表，最后删 project。IF EXISTS 同时兼容结构不完整
        # 或升级中断后再次启动的场景。
        table_names = (
            "iec61850_model_reference",
            "iec61850_model_node",
            "iec61850_model_version",
            project_table,
        )
        with engine.begin() as conn:
            for table_name in table_names:
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))

    def _migrate_goose_schema(self) -> None:
        """补齐 create_all 无法添加的 GOOSE Publisher 新列。

        Receiver/Subscription 是新表，由 create_all 创建；这里仅处理旧数据库
        已存在 goose_publisher 表的增量列。使用 inspector 保证重复执行安全。
        """
        if not self.db_config:
            return
        from sqlalchemy import inspect, text

        engine = self.db_config.engine
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        with engine.begin() as conn:
            if "goose_publisher" in table_names:
                existing = {column["name"] for column in inspector.get_columns("goose_publisher")}
                definitions = {
                    "name": "VARCHAR(128) NOT NULL DEFAULT ''",
                    "description": "VARCHAR(512) NOT NULL DEFAULT ''",
                    "auto_start": "BOOLEAN NOT NULL DEFAULT 0",
                }
                for column, ddl in definitions.items():
                    if column not in existing:
                        conn.execute(text(f"ALTER TABLE goose_publisher ADD COLUMN {column} {ddl}"))

            if "goose_subscription" in table_names:
                existing = {column["name"] for column in inspector.get_columns("goose_subscription")}
                definitions = {
                    "enabled": "BOOLEAN NOT NULL DEFAULT 0",
                    "ied_name": "VARCHAR(128) NOT NULL DEFAULT ''",
                    "ld_inst": "VARCHAR(128) NOT NULL DEFAULT ''",
                    "ln_name": "VARCHAR(128) NOT NULL DEFAULT 'LLN0'",
                    "dataset_entries_json": "TEXT",
                    "go_id": "VARCHAR(256) NOT NULL DEFAULT ''",
                }
                for column, ddl in definitions.items():
                    if column not in existing:
                        conn.execute(text(f"ALTER TABLE goose_subscription ADD COLUMN {column} {ddl}"))

    def _migrate_channel_security_schema(self) -> None:
        """补齐 TLS 字段，并迁移已移除的 basic 模式。"""
        if not self.db_config:
            return
        from sqlalchemy import inspect, text

        engine = self.db_config.engine
        inspector = inspect(engine)
        if "channel_security_config" not in inspector.get_table_names():
            return
        existing = {column["name"] for column in inspector.get_columns("channel_security_config")}
        definitions = {
            "tls_mode": "VARCHAR(16) NOT NULL DEFAULT 'one_way'",
            "ca_certificate_path": "VARCHAR(512)",
            "ca_certificate_filename": "VARCHAR(255)",
        }
        with engine.begin() as conn:
            for column, ddl in definitions.items():
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE channel_security_config ADD COLUMN {column} {ddl}"))
            conn.execute(text("UPDATE channel_security_config SET tls_mode = 'one_way' WHERE tls_mode = 'basic'"))
