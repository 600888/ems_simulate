from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from src.data.controller.db_controller import DbController


def _create_legacy_modeling_schema(db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE iec61850_model_project (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(128) NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE iec61850_model_node (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL
                )
                """
            )
        )
        conn.execute(text("INSERT INTO iec61850_model_project (id, name) VALUES ('legacy-project', 'legacy')"))
        conn.execute(text("INSERT INTO iec61850_model_node (id, project_id) VALUES ('legacy-node', 'legacy-project')"))
    engine.dispose()


def test_init_sqlite_rebuilds_legacy_iec61850_modeling_tables(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_modeling_schema(db_path)

    controller = DbController()
    assert controller.init_sqlite_db(str(db_path)) is True

    inspector = inspect(controller.engine)
    project_columns = {column["name"] for column in inspector.get_columns("iec61850_model_project")}
    assert {
        "model_json",
        "model_format_version",
        "model_node_count",
        "model_checksum",
    }.issubset(project_columns)
    assert "iec61850_model_node" not in inspector.get_table_names()

    with controller.engine.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM iec61850_model_project")) == 0

    controller.close_db()


def test_init_sqlite_keeps_current_iec61850_modeling_data(tmp_path: Path):
    db_path = tmp_path / "current.db"
    controller = DbController()
    assert controller.init_sqlite_db(str(db_path)) is True

    with controller.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO iec61850_model_project (
                    id, name, code, description, file_type, standard_version,
                    namespace, modeling_mode, status, revision,
                    validation_errors, validation_warnings, model_json,
                    model_format_version, model_node_count, model_checksum
                ) VALUES (
                    'current-project', 'current', 'CURRENT', '', 'ICD',
                    'IEC 61850 Ed2.1', '', 'FROM_SCRATCH', 'DRAFT', 1,
                    0, 0, :model_json,
                    1, 0, ''
                )
                """
            ),
            {"model_json": '{"format_version":1,"nodes":[],"references":[]}'},
        )

    # 再次初始化时，新结构不能被误判为旧结构。
    assert controller.init_sqlite_db(str(db_path)) is True
    with controller.engine.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM iec61850_model_project")) == 1

    controller.close_db()


def test_init_sqlite_adds_safe_dlt645_point_mode_to_legacy_channels(tmp_path: Path):
    db_path = tmp_path / "legacy-channel.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE channel ("
                "id INTEGER PRIMARY KEY, code VARCHAR(32), name VARCHAR(64), "
                "protocol_type INTEGER, conn_type INTEGER)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO channel (id, code, name, protocol_type, conn_type) "
                "VALUES (1, 'DLT', 'legacy DLT645', 3, 1)"
            )
        )
    engine.dispose()

    controller = DbController()
    assert controller.init_sqlite_db(str(db_path)) is True

    inspector = inspect(controller.engine)
    columns = {column["name"] for column in inspector.get_columns("channel")}
    assert "dlt645_point_mode" in columns
    with controller.engine.connect() as conn:
        assert conn.scalar(text("SELECT dlt645_point_mode FROM channel WHERE id = 1")) == "import"

    controller.close_db()


def test_init_sqlite_recognizes_a_legacy_complete_dlt645_standard_table(tmp_path: Path):
    from dlt645.model.data.define import DIMap

    db_path = tmp_path / "legacy-standard-dlt645.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE channel ("
                "id INTEGER PRIMARY KEY, code VARCHAR(32), name VARCHAR(64), "
                "protocol_type INTEGER, conn_type INTEGER)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO channel (id, code, name, protocol_type, conn_type) "
                "VALUES (1, 'DLT', 'legacy standard DLT645', 3, 1)"
            )
        )
        for table in ("point_yc", "point_yx", "point_yk", "point_yt"):
            conn.execute(text(f"CREATE TABLE {table} (channel_id INTEGER, code VARCHAR(64))"))
        conn.execute(
            text("INSERT INTO point_yc (channel_id, code) VALUES (1, :code)"),
            [{"code": f"0x{di:08X}"} for di in DIMap],
        )
    engine.dispose()

    controller = DbController()
    assert controller.init_sqlite_db(str(db_path)) is True
    with controller.engine.connect() as conn:
        assert conn.scalar(text("SELECT dlt645_point_mode FROM channel WHERE id = 1")) == "standard"

    controller.close_db()
