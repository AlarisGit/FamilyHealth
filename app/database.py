import time
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = None
SessionLocal = None


def init_db(max_retries: int = 30, retry_delay: float = 2.0):
    global engine, SessionLocal
    for attempt in range(1, max_retries + 1):
        try:
            engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
            logger.info("Database connection established.")
            return
        except Exception as e:
            logger.warning(f"DB connect attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time.sleep(retry_delay)
    raise RuntimeError("Could not connect to database after retries.")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
