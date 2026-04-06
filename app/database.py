import logging
import time
from datetime import date, time as dt_time, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL, SCHEDULE_DAYS_AHEAD
from models import DoctorSchedule, ServiceSchedule

logger = logging.getLogger(__name__)

engine = None
SessionLocal = None


def ensure_schema_compatibility():
    with engine.begin() as conn:
        # Telegram user ids do not fit into MySQL INT for all accounts.
        conn.execute(text("ALTER TABLE visit MODIFY COLUMN patient_id BIGINT NOT NULL"))


def _doctor_schedule_templates(work_date: date):
    weekday = work_date.isoweekday()
    is_weekday = weekday <= 5

    templates = [
        (1, 1, dt_time(9, 0), dt_time(17, 0)),
        (6, 3, dt_time(8, 0), dt_time(14, 0)),
    ]
    if is_weekday:
        templates.extend([
            (2, 1, dt_time(10, 0), dt_time(18, 0)),
            (3, 2, dt_time(8, 0), dt_time(16, 0)),
            (4, 3, dt_time(9, 0), dt_time(15, 0)),
            (8, 2, dt_time(8, 0), dt_time(16, 0)),
            (9, 1, dt_time(11, 0), dt_time(19, 0)),
        ])
    if weekday in (1, 3, 5):
        templates.extend([
            (5, 1, dt_time(10, 0), dt_time(14, 0)),
            (10, 3, dt_time(9, 0), dt_time(15, 0)),
        ])
    if weekday in (2, 4):
        templates.append((7, 2, dt_time(9, 0), dt_time(17, 0)))
    return templates


def _service_schedule_templates(work_date: date):
    weekday = work_date.isoweekday()
    is_weekday = weekday <= 5

    templates = [
        (1, dt_time(7, 0), dt_time(12, 0)),
        (5, dt_time(8, 0), dt_time(16, 0)),
    ]
    if is_weekday:
        templates.extend([
            (2, dt_time(8, 0), dt_time(17, 0)),
            (3, dt_time(8, 0), dt_time(20, 0)),
            (4, dt_time(8, 0), dt_time(18, 0)),
            (6, dt_time(9, 0), dt_time(15, 0)),
        ])
    return templates


def ensure_future_schedules(days_ahead: int = SCHEDULE_DAYS_AHEAD):
    today = date.today()
    target_end = today + timedelta(days=max(days_ahead - 1, 0))

    db = SessionLocal()
    try:
        existing_doctor_keys = {
            (doctor_id, clinic_id, work_date, time_start, time_end)
            for doctor_id, clinic_id, work_date, time_start, time_end in (
                db.query(
                    DoctorSchedule.doctor_id,
                    DoctorSchedule.clinic_id,
                    DoctorSchedule.work_date,
                    DoctorSchedule.time_start,
                    DoctorSchedule.time_end,
                )
                .filter(DoctorSchedule.work_date >= today, DoctorSchedule.work_date <= target_end)
                .all()
            )
        }
        existing_service_keys = {
            (service_id, work_date, time_start, time_end)
            for service_id, work_date, time_start, time_end in (
                db.query(
                    ServiceSchedule.service_id,
                    ServiceSchedule.work_date,
                    ServiceSchedule.time_start,
                    ServiceSchedule.time_end,
                )
                .filter(ServiceSchedule.work_date >= today, ServiceSchedule.work_date <= target_end)
                .all()
            )
        }

        new_doctor_rows = []
        new_service_rows = []

        current = today
        while current <= target_end:
            if current.isoweekday() != 7:
                for doctor_id, clinic_id, time_start, time_end in _doctor_schedule_templates(current):
                    key = (doctor_id, clinic_id, current, time_start, time_end)
                    if key not in existing_doctor_keys:
                        new_doctor_rows.append(
                            DoctorSchedule(
                                doctor_id=doctor_id,
                                clinic_id=clinic_id,
                                work_date=current,
                                time_start=time_start,
                                time_end=time_end,
                            )
                        )
                        existing_doctor_keys.add(key)

                for service_id, time_start, time_end in _service_schedule_templates(current):
                    key = (service_id, current, time_start, time_end)
                    if key not in existing_service_keys:
                        new_service_rows.append(
                            ServiceSchedule(
                                service_id=service_id,
                                work_date=current,
                                time_start=time_start,
                                time_end=time_end,
                            )
                        )
                        existing_service_keys.add(key)

            current += timedelta(days=1)

        if new_doctor_rows or new_service_rows:
            db.add_all(new_doctor_rows + new_service_rows)
            db.commit()
            logger.info(
                "Extended schedules through %s (%s doctor rows, %s service rows).",
                target_end.isoformat(),
                len(new_doctor_rows),
                len(new_service_rows),
            )
    finally:
        db.close()


def init_db(max_retries: int = 30, retry_delay: float = 2.0):
    global engine, SessionLocal
    for attempt in range(1, max_retries + 1):
        try:
            engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            ensure_schema_compatibility()
            SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
            ensure_future_schedules()
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
