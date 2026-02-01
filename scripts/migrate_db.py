import sys
import os
import sqlite3
import shutil

# Add project root to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from src.config.global_config import ROOT_DIR
from src.config.config import Config
from src.data.model.base import Base
# Import all models to ensure they are registered with Base.metadata
from src.data.model.channel import Channel
from src.data.model.point_yc import PointYc
from src.data.model.point_yx import PointYx
from src.data.model.point_yk import PointYk
from src.data.model.point_yt import PointYt
from sqlalchemy import create_engine, text
import logging

# Configure logging
logging.basicConfig(filename='migration_debug.log', level=logging.INFO, 
                    format='%(asctime)s - %(message)s', encoding='utf-8')

def migrate():
    print("Starting database migration...")
    logging.info("Starting database migration...")
    
    # Load config to get DB path
    config_path = os.path.join(ROOT_DIR, "etc", "config.ini")
    if not os.path.exists(config_path):
        config_path = os.path.join(ROOT_DIR, "config.ini")
    Config.load_config(config_path)
    
    if not Config.is_sqlite():
        print("Migration script currently only supports SQLite.")
        return

    db_path = os.path.join(ROOT_DIR, Config.sqlite_path)
    print(f"Database path: {db_path}")
    
    if not os.path.exists(db_path):
        print("Database file not found. Nothing to migrate.")
        return

    # Backup DB
    backup_path = db_path + ".bak"
    shutil.copy2(db_path, backup_path)
    print(f"Backup created at: {backup_path}")

    engine = create_engine(f"sqlite:///{db_path}")
    
    tables_to_migrate = ["point_yc", "point_yx", "point_yk", "point_yt"]
    
    with engine.connect() as conn:
        for table_name in tables_to_migrate:
            print(f"Migrating table: {table_name}")
            
            # Check if table exists
            exists = conn.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")).fetchone()
            if not exists:
                print(f"Table {table_name} does not exist, skipping.")
                continue

            # Rename old table
            old_table_name = f"{table_name}_old"
            conn.execute(text(f"DROP TABLE IF EXISTS {old_table_name}"))
            conn.execute(text(f"ALTER TABLE {table_name} RENAME TO {old_table_name}"))
            
    # Create new tables
    print("Creating new tables...")
    Base.metadata.create_all(engine)
    
    with engine.connect() as conn:
        for table_name in tables_to_migrate:
            old_table_name = f"{table_name}_old"
            
            # Check if old table exists (it might have been skipped if it didn't exist originally)
            exists = conn.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{old_table_name}'")).fetchone()
            if not exists:
                continue

            print(f"Copying data for {table_name}...")
            
            # Get columns for new table
            new_columns = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            new_col_names = set(c[1] for c in new_columns)
            logging.info(f"New table {table_name} columns: {new_col_names}")
            
            # Get columns for old table
            old_columns = conn.execute(text(f"PRAGMA table_info({old_table_name})")).fetchall()
            old_col_names = set(c[1] for c in old_columns)
            logging.info(f"Old table {old_table_name} columns: {old_col_names}")
            
            # Intersect columns
            common_cols = list(new_col_names.intersection(old_col_names))
            logging.info(f"Common columns: {common_cols}")
            
            if not common_cols:
                print(f"No common columns for {table_name}, skipping data copy.")
                logging.warning(f"No common columns for {table_name}")
                continue
                
            cols_str = ", ".join([f'"{c}"' for c in common_cols])
            sql_query = f"INSERT INTO {table_name} ({cols_str}) SELECT {cols_str} FROM {old_table_name}"
            logging.info(f"Executing SQL: {sql_query}")
            
            try:
                conn.execute(text(sql_query))
                conn.commit()
                print(f"Data copied for {table_name}.")
                logging.info(f"Data copied for {table_name}.")
                
                # Drop old table
                conn.execute(text(f"DROP TABLE {old_table_name}"))
            except Exception as e:
                logging.error(f"Error copying data for {table_name}: {e}")
                print(f"Error copying data for {table_name}: {e}")
                print(f"Error copying data for {table_name}: {e}")
                print("Restoring from backup is recommended if this fails.")
                raise e

    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
