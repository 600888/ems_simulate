from sqlalchemy import text

from src.config.db.db_config import DbMysqlConfig, DbSqliteConfig


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
