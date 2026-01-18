
import sqlite3
import os

db_path = "data/ems.db"

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 删除四个测点表
    tables = ["point_yc", "point_yx", "point_yk", "point_yt"]
    for table in tables:
        print(f"Dropping table {table}...")
        cursor.execute(f"DROP TABLE IF EXISTS {table}")
    
    conn.commit()
    conn.close()
    print("Point tables dropped successfully. Please restart the backend to recreate them.")
else:
    print(f"Database not found at {db_path}")
