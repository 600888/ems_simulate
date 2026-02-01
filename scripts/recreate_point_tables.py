import sys
import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add project root to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from src.config.global_config import ROOT_DIR
from src.config.config import Config
from src.data.model.base import Base
from src.data.model.channel import Channel # Dependency
from src.data.model.point_yc import PointYc
from src.data.model.point_yx import PointYx
from src.data.model.point_yk import PointYk
from src.data.model.point_yt import PointYt

# Configure logging
logging.basicConfig(filename='recreate_debug.log', level=logging.INFO, 
                    format='%(asctime)s - %(message)s', encoding='utf-8')

def migrate():
    logging.info("Starting database table recreation...")
    print("Starting...")
    
    # Load config
    config_path = os.path.join(ROOT_DIR, "etc", "config.ini")
    if not os.path.exists(config_path):
        config_path = os.path.join(ROOT_DIR, "config.ini")
    Config.load_config(config_path)
    
    if not Config.is_sqlite():
        logging.error("Script only supports SQLite.")
        return

    db_path = os.path.join(ROOT_DIR, Config.sqlite_path)
    if not os.path.exists(db_path):
        logging.error(f"Database not found at {db_path}")
        return

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    tables = [
        ("point_yc", PointYc),
        ("point_yx", PointYx),
        ("point_yk", PointYk),
        ("point_yt", PointYt)
    ]
    
    collected_data = {}

    try:
        # 1. Read existing data using raw SQL
        with engine.connect() as conn:
            for table_name, model_cls in tables:
                logging.info(f"Reading data from {table_name}...")
                # Check if table exists
                exists = conn.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")).fetchone()
                if not exists:
                    logging.warning(f"Table {table_name} does not exist, skipping read.")
                    collected_data[table_name] = []
                    continue

                # Get columns to map rows to dicts
                # PRAGMA table_info gives (cid, name, type, notnull, dflt_value, pk)
                columns = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
                col_names = [c[1] for c in columns]
                
                rows = conn.execute(text(f"SELECT * FROM {table_name}")).fetchall()
                data_list = []
                for row in rows:
                    data_list.append(dict(zip(col_names, row)))
                
                collected_data[table_name] = data_list
                logging.info(f"Read {len(data_list)} rows from {table_name}.")

        # 2. Drop current tables and indexes explicitly
        with engine.connect() as conn:
            for table_name, _ in tables:
                logging.info(f"Cleaning up {table_name}...")
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}_old"))
                
                # Drop known indexes just in case
                indexes = [
                    f"ix_{table_name}_code",
                    f"ix_{table_name}_channel_id"
                ]
                for idx in indexes:
                    conn.execute(text(f"DROP INDEX IF EXISTS {idx}"))
                    
            conn.commit()

        # 3. Create new tables
        logging.info("Recreating tables...")
        # Base.metadata.create_all checks existence, but since we dropped them, it will create.
        Base.metadata.create_all(engine)

        # 4. Insert data using ORM
        for table_name, model_cls in tables:
            data_list = collected_data.get(table_name, [])
            if not data_list:
                continue
                
            logging.info(f"Inserting {len(data_list)} rows into {table_name}...")
            
            # Inspect model columns to filter input data
            model_columns = {c.name for c in model_cls.__table__.columns}
            
            for row_dict in data_list:
                # Filter valid columns
                valid_data = {k: v for k, v in row_dict.items() if k in model_columns}
                
                # Create object
                obj = model_cls(**valid_data)
                session.add(obj)
            
            session.commit() # Commit per table to save progress
            logging.info(f"Inserted rows for {table_name}.")

        logging.info("Migration completed successfully.")

    except Exception as e:
        logging.error(f"Migration failed: {e}")
        with open("error.txt", "w", encoding="utf-8") as f:
            f.write(str(e))
            import traceback
            f.write("\n")
            traceback.print_exc(file=f)
        session.rollback()
        raise e
    finally:
        session.close()

if __name__ == "__main__":
    migrate()
