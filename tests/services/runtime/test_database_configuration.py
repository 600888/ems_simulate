from unittest.mock import MagicMock

from pymysql.err import OperationalError as MysqlOperationalError
import pytest
from sqlalchemy import text
from sqlalchemy.dialects.mysql import dialect
from sqlalchemy.exc import OperationalError

from src.config.db import db_config
from src.config.db.db_config import DbMysqlAsyncConfig, DbMysqlConfig, DbSqliteConfig
from src.data.controller import db_controller


def test_sqlite_connections_enable_integrity_and_concurrency_pragmas(tmp_path):
    config = DbSqliteConfig()
    config.set_db_path(str(tmp_path / "runtime.db"))
    config.create_engine()
    try:
        with config.engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
            assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000
            assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    finally:
        config.close_engine()


def test_mysql_url_masks_password_in_logs():
    config = DbMysqlConfig()
    config.set_db_config("localhost", "3306", "user", "secret:value")

    url = config.get_url("ems")

    assert "secret:value" not in str(url)
    assert url.password == "secret:value"


def _mysql_error(code):
    return OperationalError(None, None, MysqlOperationalError(code, "MySQL error"))


@pytest.mark.parametrize("asynchronous", [False, True])
def test_mysql_creates_missing_database_without_selecting_it(monkeypatch, asynchronous):
    probe, server, runtime = MagicMock(), MagicMock(), MagicMock()
    probe.connect.side_effect = _mysql_error(1049)
    server.dialect = dialect()
    factory = MagicMock(side_effect=[probe, server] if asynchronous else [probe, server, runtime])
    monkeypatch.setattr(db_config, "create_engine", factory)
    async_factory = MagicMock(return_value=runtime)
    monkeypatch.setattr(db_config, "create_async_engine", async_factory)
    config = DbMysqlAsyncConfig() if asynchronous else DbMysqlConfig()
    config.set_db_config("localhost", "3307", "user", "secret:@/value")
    db_name = "ems-测试`db"

    if asynchronous:
        config.create_async_engine(db_name)
    else:
        config.create_engine(db_name)

    probe_url = factory.call_args_list[0].args[0]
    server_url = factory.call_args_list[1].args[0]
    assert probe_url.database == db_name
    assert probe_url.drivername == "mysql+pymysql"
    assert server_url.database is None
    assert server_url.host == "localhost"
    assert server_url.port == 3307
    assert server_url.username == "user"
    assert server_url.password == "secret:@/value"
    assert factory.call_args_list[1].kwargs["isolation_level"] == "AUTOCOMMIT"
    server.connect.return_value.__enter__.return_value.exec_driver_sql.assert_called_once_with(
        "CREATE DATABASE IF NOT EXISTS `ems-测试``db` CHARACTER SET utf8mb4"
    )
    runtime_url = (async_factory if asynchronous else factory).call_args.args[0]
    assert runtime_url.database == db_name
    assert runtime_url.drivername == ("mysql+aiomysql" if asynchronous else "mysql+pymysql")
    assert config.engine is runtime
    probe.dispose.assert_called_once()
    server.dispose.assert_called_once()


def test_mysql_existing_database_does_not_issue_create_or_drop(monkeypatch):
    probe, runtime = MagicMock(), MagicMock()
    factory = MagicMock(side_effect=[probe, runtime])
    monkeypatch.setattr(db_config, "create_engine", factory)

    config = DbMysqlConfig()
    config.create_engine("ems")

    assert factory.call_count == 2
    assert all(call.args[0].database == "ems" for call in factory.call_args_list)
    connection = probe.connect.return_value.__enter__.return_value
    connection.execute.assert_not_called()
    connection.exec_driver_sql.assert_not_called()
    probe.dispose.assert_called_once()
    assert config.engine is runtime


@pytest.mark.parametrize("code", [1044, 1045, 2003])
def test_mysql_does_not_create_database_for_permission_or_connection_errors(monkeypatch, code):
    probe = MagicMock()
    error = _mysql_error(code)
    probe.connect.side_effect = error
    factory = MagicMock(return_value=probe)
    monkeypatch.setattr(db_config, "create_engine", factory)

    with pytest.raises(OperationalError) as caught:
        DbMysqlConfig().create_engine("ems")

    assert caught.value is error
    factory.assert_called_once()
    probe.dispose.assert_called_once()


def test_mysql_disposes_server_connection_when_creation_fails(monkeypatch):
    probe, server = MagicMock(), MagicMock()
    probe.connect.side_effect = _mysql_error(1049)
    server.dialect = dialect()
    error = _mysql_error(1044)
    server.connect.return_value.__enter__.return_value.exec_driver_sql.side_effect = error
    factory = MagicMock(side_effect=[probe, server])
    monkeypatch.setattr(db_config, "create_engine", factory)

    with pytest.raises(OperationalError) as caught:
        DbMysqlConfig().create_engine("ems")

    assert caught.value is error
    assert factory.call_count == 2
    probe.dispose.assert_called_once()
    server.dispose.assert_called_once()


def test_mysql_can_explicitly_disable_database_creation(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(db_config, "create_engine", factory)

    DbMysqlConfig().create_engine("ems", is_create_db=False)

    factory.assert_called_once()
    factory.return_value.connect.assert_not_called()


@pytest.mark.parametrize("initialization_fails", [False, True])
def test_mysql_controller_ensures_database_before_schema_initialization(monkeypatch, initialization_fails):
    controller = db_controller.DbController()
    config = MagicMock()
    config_factory = MagicMock(return_value=config)
    monkeypatch.setattr(db_controller, "DbMysqlConfig", config_factory)
    if initialization_fails:
        config.create_engine.side_effect = _mysql_error(1044)
    steps = MagicMock()
    steps.attach_mock(config.create_engine, "ensure_database")
    for method in (
        "_reset_legacy_iec61850_modeling_schema",
        "_migrate_channel_point_table_mode_schema",
        "_migrate_dnp3_point_config_schema",
        "_migrate_goose_schema",
        "_migrate_channel_security_schema",
    ):
        operation = MagicMock()
        monkeypatch.setattr(controller, method, operation)
        steps.attach_mock(operation, method)
    create_tables = MagicMock()
    monkeypatch.setattr(db_controller.Base.metadata, "create_all", create_tables)
    steps.attach_mock(create_tables, "create_tables")

    result = controller.init_db(
        "mysql", ip="localhost", port="3307", user_name="user", pass_word="secret", database="ems"
    )

    assert result is (not initialization_fails)
    config.set_db_config.assert_called_once_with("localhost", "3307", "user", "secret")
    config.create_engine.assert_called_once_with("ems")
    assert steps.mock_calls[0][0] == "ensure_database"
    if initialization_fails:
        assert len(steps.mock_calls) == 1
    else:
        create_tables.assert_called_once_with(config.engine)
        assert len(steps.mock_calls) == 7
