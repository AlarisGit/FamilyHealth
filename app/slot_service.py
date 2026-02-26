"""Slot generation and booking logic."""

from datetime import datetime, timedelta, date, time as dt_time
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text

from models import (
    Doctor, Service, Clinic, Direction,
    DoctorSchedule, ServiceSchedule, Visit,
    doctor_direction,
)


def _combine(d: date, t: dt_time) -> datetime:
    return datetime.combine(d, t)


def _doctor_name(doc: Doctor) -> str:
    parts = [doc.last_name, doc.first_name]
    if doc.middle_name:
        parts.append(doc.middle_name)
    return " ".join(parts)


def _get_doctor_visits(db: Session, doctor_id: int, day: date) -> List[Visit]:
    return (
        db.query(Visit)
        .filter(
            Visit.visit_type == "DOCTOR",
            Visit.doctor_id == doctor_id,
            Visit.start_datetime >= _combine(day, dt_time(0, 0)),
            Visit.start_datetime < _combine(day + timedelta(days=1), dt_time(0, 0)),
        )
        .all()
    )


def _get_service_visits(db: Session, service_id: int, day: date) -> List[Visit]:
    return (
        db.query(Visit)
        .filter(
            Visit.visit_type == "SERVICE",
            Visit.service_id == service_id,
            Visit.start_datetime >= _combine(day, dt_time(0, 0)),
            Visit.start_datetime < _combine(day + timedelta(days=1), dt_time(0, 0)),
        )
        .all()
    )


def _overlaps(start: datetime, duration: int, buffer: int, visits: List[Visit]) -> Optional[int]:
    """Check if [start, start+duration+buffer) overlaps any visit interval.
    Returns the patient_id of the conflicting visit, or None if free."""
    end = start + timedelta(minutes=duration + buffer)
    for v in visits:
        v_end = v.start_datetime + timedelta(minutes=v.duration_minutes + v.buffer_minutes)
        if start < v_end and end > v.start_datetime:
            return v.patient_id
    return None


def search_doctor_slots(
    db: Session,
    time_from: datetime,
    time_to: datetime,
    district: Optional[str] = None,
    clinic_id: Optional[int] = None,
    direction_id: Optional[int] = None,
    doctor_name: Optional[str] = None,
    include_busy: bool = False,
    is_admin: bool = False,
) -> list:
    query = db.query(DoctorSchedule).join(Doctor).join(Clinic)

    if district:
        query = query.filter(Clinic.district == district)
    if clinic_id:
        query = query.filter(DoctorSchedule.clinic_id == clinic_id)
    if direction_id:
        query = query.filter(
            Doctor.id.in_(
                db.query(doctor_direction.c.doctor_id)
                .filter(doctor_direction.c.direction_id == direction_id)
            )
        )
    if doctor_name:
        pattern = f"%{doctor_name}%"
        query = query.filter(
            or_(
                Doctor.first_name.ilike(pattern),
                Doctor.last_name.ilike(pattern),
                Doctor.middle_name.ilike(pattern),
            )
        )

    query = query.filter(
        DoctorSchedule.work_date >= time_from.date(),
        DoctorSchedule.work_date <= time_to.date(),
    )

    schedules = query.all()

    slots = []
    for sched in schedules:
        doc = sched.doctor
        clinic = sched.clinic
        window_start = _combine(sched.work_date, sched.time_start)
        window_end = _combine(sched.work_date, sched.time_end)

        visits = _get_doctor_visits(db, doc.id, sched.work_date)

        t = max(window_start, time_from)
        # Align to minute
        if t.second > 0 or t.microsecond > 0:
            t = t.replace(second=0, microsecond=0) + timedelta(minutes=1)

        while t + timedelta(minutes=doc.duration_minutes) <= window_end and t < time_to:
            busy_pid = _overlaps(t, doc.duration_minutes, doc.buffer_minutes, visits)
            is_free = busy_pid is None

            if is_free or (include_busy and is_admin):
                slot = {
                    "slot_type": "DOCTOR",
                    "clinic_id": clinic.id,
                    "clinic_name": clinic.name,
                    "district": clinic.district,
                    "doctor_id": doc.id,
                    "doctor_name": _doctor_name(doc),
                    "service_id": None,
                    "service_name": None,
                    "start": t.strftime("%Y-%m-%dT%H:%M:%S"),
                    "end": (t + timedelta(minutes=doc.duration_minutes)).strftime("%Y-%m-%dT%H:%M:%S"),
                    "is_free": is_free,
                    "busy_patient_id": busy_pid if is_admin else None,
                }
                slots.append(slot)
            t += timedelta(minutes=1)

    slots.sort(key=lambda s: (s["start"], s["doctor_name"] or ""))
    return slots


def search_service_slots(
    db: Session,
    time_from: datetime,
    time_to: datetime,
    district: Optional[str] = None,
    clinic_id: Optional[int] = None,
    service_id: Optional[int] = None,
    include_busy: bool = False,
    is_admin: bool = False,
) -> list:
    query = db.query(ServiceSchedule).join(Service).join(Clinic, Service.clinic_id == Clinic.id)

    if district:
        query = query.filter(Clinic.district == district)
    if clinic_id:
        query = query.filter(Service.clinic_id == clinic_id)
    if service_id:
        query = query.filter(ServiceSchedule.service_id == service_id)

    query = query.filter(
        ServiceSchedule.work_date >= time_from.date(),
        ServiceSchedule.work_date <= time_to.date(),
    )

    schedules = query.all()

    slots = []
    for sched in schedules:
        svc = sched.service
        clinic = svc.clinic
        window_start = _combine(sched.work_date, sched.time_start)
        window_end = _combine(sched.work_date, sched.time_end)

        visits = _get_service_visits(db, svc.id, sched.work_date)

        t = max(window_start, time_from)
        if t.second > 0 or t.microsecond > 0:
            t = t.replace(second=0, microsecond=0) + timedelta(minutes=1)

        while t + timedelta(minutes=svc.duration_minutes) <= window_end and t < time_to:
            busy_pid = _overlaps(t, svc.duration_minutes, svc.buffer_minutes, visits)
            is_free = busy_pid is None

            if is_free or (include_busy and is_admin):
                slot = {
                    "slot_type": "SERVICE",
                    "clinic_id": clinic.id,
                    "clinic_name": clinic.name,
                    "district": clinic.district,
                    "doctor_id": None,
                    "doctor_name": None,
                    "service_id": svc.id,
                    "service_name": svc.name,
                    "start": t.strftime("%Y-%m-%dT%H:%M:%S"),
                    "end": (t + timedelta(minutes=svc.duration_minutes)).strftime("%Y-%m-%dT%H:%M:%S"),
                    "is_free": is_free,
                    "busy_patient_id": busy_pid if is_admin else None,
                }
                slots.append(slot)
            t += timedelta(minutes=1)

    slots.sort(key=lambda s: (s["start"], s["service_name"] or ""))
    return slots


def book_visit(
    db: Session,
    patient_id: int,
    visit_type: str,
    doctor_id: Optional[int],
    service_id: Optional[int],
    clinic_id: Optional[int],
    start: datetime,
) -> Tuple[Optional[int], Optional[str]]:
    """Book a visit. Returns (visit_id, None) on success or (None, error_code) on failure."""

    if visit_type == "DOCTOR":
        if not doctor_id:
            return None, "invalid_request"
        doc = db.query(Doctor).filter(Doctor.id == doctor_id).first()
        if not doc:
            return None, "not_found"
        if not clinic_id:
            return None, "invalid_request"
        clinic = db.query(Clinic).filter(Clinic.id == clinic_id).first()
        if not clinic:
            return None, "not_found"

        duration = doc.duration_minutes
        buffer = doc.buffer_minutes

        # Check schedule
        sched = (
            db.query(DoctorSchedule)
            .filter(
                DoctorSchedule.doctor_id == doctor_id,
                DoctorSchedule.clinic_id == clinic_id,
                DoctorSchedule.work_date == start.date(),
                DoctorSchedule.time_start <= start.time(),
            )
            .all()
        )
        in_schedule = False
        for s in sched:
            ws = _combine(s.work_date, s.time_start)
            we = _combine(s.work_date, s.time_end)
            if start >= ws and start + timedelta(minutes=duration) <= we:
                in_schedule = True
                break
        if not in_schedule:
            return None, "not_in_schedule"

        # Idempotency check
        existing = (
            db.query(Visit)
            .filter(
                Visit.visit_type == "DOCTOR",
                Visit.doctor_id == doctor_id,
                Visit.start_datetime == start,
            )
            .first()
        )
        if existing:
            if existing.patient_id == patient_id:
                return existing.id, None
            else:
                return None, "slot_busy"

        # Overlap check
        visits = _get_doctor_visits(db, doctor_id, start.date())
        if _overlaps(start, duration, buffer, visits) is not None:
            return None, "slot_busy"

        visit = Visit(
            patient_id=patient_id,
            visit_type="DOCTOR",
            doctor_id=doctor_id,
            service_id=None,
            clinic_id=clinic_id,
            start_datetime=start,
            duration_minutes=duration,
            buffer_minutes=buffer,
            created_at=datetime.now(),
        )
        db.add(visit)
        try:
            db.commit()
        except Exception:
            db.rollback()
            return None, "slot_busy"
        db.refresh(visit)
        return visit.id, None

    elif visit_type == "SERVICE":
        if not service_id:
            return None, "invalid_request"
        svc = db.query(Service).filter(Service.id == service_id).first()
        if not svc:
            return None, "not_found"

        derived_clinic_id = svc.clinic_id
        duration = svc.duration_minutes
        buffer = svc.buffer_minutes

        # Check schedule
        sched = (
            db.query(ServiceSchedule)
            .filter(
                ServiceSchedule.service_id == service_id,
                ServiceSchedule.work_date == start.date(),
                ServiceSchedule.time_start <= start.time(),
            )
            .all()
        )
        in_schedule = False
        for s in sched:
            ws = _combine(s.work_date, s.time_start)
            we = _combine(s.work_date, s.time_end)
            if start >= ws and start + timedelta(minutes=duration) <= we:
                in_schedule = True
                break
        if not in_schedule:
            return None, "not_in_schedule"

        # Idempotency check
        existing = (
            db.query(Visit)
            .filter(
                Visit.visit_type == "SERVICE",
                Visit.service_id == service_id,
                Visit.start_datetime == start,
            )
            .first()
        )
        if existing:
            if existing.patient_id == patient_id:
                return existing.id, None
            else:
                return None, "slot_busy"

        # Overlap check
        visits = _get_service_visits(db, service_id, start.date())
        if _overlaps(start, duration, buffer, visits) is not None:
            return None, "slot_busy"

        visit = Visit(
            patient_id=patient_id,
            visit_type="SERVICE",
            doctor_id=None,
            service_id=service_id,
            clinic_id=derived_clinic_id,
            start_datetime=start,
            duration_minutes=duration,
            buffer_minutes=buffer,
            created_at=datetime.now(),
        )
        db.add(visit)
        try:
            db.commit()
        except Exception:
            db.rollback()
            return None, "slot_busy"
        db.refresh(visit)
        return visit.id, None

    return None, "invalid_request"
