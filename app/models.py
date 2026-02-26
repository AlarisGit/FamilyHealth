from sqlalchemy import (
    Column, Integer, String, Text, Date, Time, DateTime, Enum, ForeignKey,
    Table
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

doctor_direction = Table(
    "doctor_direction",
    Base.metadata,
    Column("doctor_id", Integer, ForeignKey("doctor.id"), primary_key=True),
    Column("direction_id", Integer, ForeignKey("direction.id"), primary_key=True),
)


class Clinic(Base):
    __tablename__ = "clinic"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    district = Column(String(100), nullable=False)
    address = Column(String(300), nullable=False)


class Direction(Base):
    __tablename__ = "direction"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)


class Doctor(Base):
    __tablename__ = "doctor"
    id = Column(Integer, primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    middle_name = Column(String(100))
    bio_text = Column(Text)
    photo_path = Column(String(300))
    duration_minutes = Column(Integer, nullable=False, default=30)
    buffer_minutes = Column(Integer, nullable=False, default=0)

    directions = relationship("Direction", secondary=doctor_direction, lazy="joined")


class Service(Base):
    __tablename__ = "service"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    clinic_id = Column(Integer, ForeignKey("clinic.id"), nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=30)
    buffer_minutes = Column(Integer, nullable=False, default=0)

    clinic = relationship("Clinic", lazy="joined")


class DoctorSchedule(Base):
    __tablename__ = "doctor_schedule"
    id = Column(Integer, primary_key=True)
    doctor_id = Column(Integer, ForeignKey("doctor.id"), nullable=False)
    clinic_id = Column(Integer, ForeignKey("clinic.id"), nullable=False)
    work_date = Column(Date, nullable=False)
    time_start = Column(Time, nullable=False)
    time_end = Column(Time, nullable=False)

    doctor = relationship("Doctor", lazy="joined")
    clinic = relationship("Clinic", lazy="joined")


class ServiceSchedule(Base):
    __tablename__ = "service_schedule"
    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey("service.id"), nullable=False)
    work_date = Column(Date, nullable=False)
    time_start = Column(Time, nullable=False)
    time_end = Column(Time, nullable=False)

    service = relationship("Service", lazy="joined")


class Visit(Base):
    __tablename__ = "visit"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    visit_type = Column(Enum("DOCTOR", "SERVICE"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctor.id"))
    service_id = Column(Integer, ForeignKey("service.id"))
    clinic_id = Column(Integer, ForeignKey("clinic.id"), nullable=False)
    start_datetime = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    buffer_minutes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)

    doctor = relationship("Doctor", lazy="joined")
    service = relationship("Service", lazy="joined")
    clinic = relationship("Clinic", lazy="joined")
