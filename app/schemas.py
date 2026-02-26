from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


class VisitTypeEnum(str, Enum):
    DOCTOR = "DOCTOR"
    SERVICE = "SERVICE"


class SlotItem(BaseModel):
    slot_type: str
    clinic_id: int
    clinic_name: str
    district: str
    doctor_id: Optional[int] = None
    doctor_name: Optional[str] = None
    doctor_directions: Optional[str] = None
    service_id: Optional[int] = None
    service_name: Optional[str] = None
    start: str
    end: str
    is_free: bool
    busy_patient_id: Optional[int] = None


class SlotSearchResponse(BaseModel):
    items: List[SlotItem]


class BookVisitRequest(BaseModel):
    visit_type: VisitTypeEnum
    doctor_id: Optional[int] = None
    service_id: Optional[int] = None
    clinic_id: Optional[int] = None
    start: str


class BookVisitResponse(BaseModel):
    visit_id: int
    status: str = "booked"


class VisitItem(BaseModel):
    visit_id: int
    patient_id: int
    visit_type: str
    clinic_id: int
    clinic_name: str
    doctor_id: Optional[int] = None
    doctor_name: Optional[str] = None
    service_id: Optional[int] = None
    service_name: Optional[str] = None
    start: str
    end: str


class VisitListResponse(BaseModel):
    items: List[VisitItem]


class DeleteResponse(BaseModel):
    status: str = "deleted"


class ErrorResponse(BaseModel):
    error: str
    message: str


class ClinicItem(BaseModel):
    id: int
    name: str
    district: str
    address: str


class DirectionItem(BaseModel):
    id: int
    name: str


class DoctorItem(BaseModel):
    id: int
    first_name: str
    last_name: str
    middle_name: Optional[str] = None
    bio_text: Optional[str] = None
    photo_path: Optional[str] = None
    duration_minutes: int
    buffer_minutes: int
    directions: List[DirectionItem] = []


class ServiceItem(BaseModel):
    id: int
    name: str
    clinic_id: int
    clinic_name: str
    duration_minutes: int
    buffer_minutes: int
