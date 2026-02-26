import os

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "family_health")
DB_USER = os.getenv("DB_USER", "family_health")
DB_PASSWORD = os.getenv("DB_PASSWORD", "demo_pw")
APP_PORT = int(os.getenv("APP_PORT", "8080"))

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)
