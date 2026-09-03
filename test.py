import os
from pathlib import Path
import mysql.connector
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=True)

try:
    conn = mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "counselling_system")
    )

    print("Connected successfully!")
    print("Server:", conn.server_info)

    conn.close()

except Exception as e:
    print("ERROR:", e)
