import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from config import APP_PORT
from database import init_db, get_db
from models import Clinic, Direction, Doctor, Service, Visit, doctor_direction
from schemas import (
    SlotSearchResponse, BookVisitRequest, BookVisitResponse,
    VisitListResponse, VisitItem, DeleteResponse, ErrorResponse,
    ClinicItem, DirectionItem, DoctorItem, ServiceItem,
)
from slot_service import (
    search_doctor_slots, search_service_slots, book_visit, _doctor_name,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Family Health - Visit Scheduling (Demo)",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def startup():
    init_db()


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------
def error_response(status_code: int, error: str, message: str):
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "message": message},
    )


# ---------------------------------------------------------------------------
# Reference data endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/clinics", response_model=list[ClinicItem], tags=["Reference Data"])
def list_clinics(db: Session = Depends(get_db)):
    rows = db.query(Clinic).order_by(Clinic.name).all()
    return [ClinicItem(id=c.id, name=c.name, district=c.district, address=c.address) for c in rows]


@app.get("/api/v1/directions", response_model=list[DirectionItem], tags=["Reference Data"])
def list_directions(db: Session = Depends(get_db)):
    rows = db.query(Direction).order_by(Direction.name).all()
    return [DirectionItem(id=d.id, name=d.name) for d in rows]


@app.get("/api/v1/doctors", response_model=list[DoctorItem], tags=["Reference Data"])
def list_doctors(
    direction_id: Optional[int] = Query(None),
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Doctor)
    if direction_id:
        q = q.filter(
            Doctor.id.in_(
                db.query(doctor_direction.c.doctor_id)
                .filter(doctor_direction.c.direction_id == direction_id)
            )
        )
    if name:
        pattern = f"%{name}%"
        q = q.filter(
            or_(
                Doctor.first_name.ilike(pattern),
                Doctor.last_name.ilike(pattern),
                Doctor.middle_name.ilike(pattern),
            )
        )
    rows = q.order_by(Doctor.last_name, Doctor.first_name).all()
    result = []
    for doc in rows:
        result.append(DoctorItem(
            id=doc.id,
            first_name=doc.first_name,
            last_name=doc.last_name,
            middle_name=doc.middle_name,
            bio_text=doc.bio_text,
            photo_path=doc.photo_path,
            duration_minutes=doc.duration_minutes,
            buffer_minutes=doc.buffer_minutes,
            directions=[DirectionItem(id=d.id, name=d.name) for d in doc.directions],
        ))
    return result


@app.get("/api/v1/services", response_model=list[ServiceItem], tags=["Reference Data"])
def list_services(
    clinic_id: Optional[int] = Query(None),
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Service)
    if clinic_id:
        q = q.filter(Service.clinic_id == clinic_id)
    if name:
        q = q.filter(Service.name.ilike(f"%{name}%"))
    rows = q.order_by(Service.name).all()
    return [
        ServiceItem(
            id=s.id, name=s.name, clinic_id=s.clinic_id,
            clinic_name=s.clinic.name,
            duration_minutes=s.duration_minutes,
            buffer_minutes=s.buffer_minutes,
        )
        for s in rows
    ]


# ---------------------------------------------------------------------------
# Slots search
# ---------------------------------------------------------------------------
@app.get("/api/v1/slots/search", response_model=SlotSearchResponse, tags=["Slots"])
def api_search_slots(
    patient_id: int = Query(...),
    type: str = Query(..., pattern="^(doctor|service)$"),
    time_from: str = Query(...),
    time_to: str = Query(...),
    district: Optional[str] = Query(None),
    clinic_id: Optional[int] = Query(None),
    direction_id: Optional[int] = Query(None),
    doctor_name: Optional[str] = Query(None),
    service_id: Optional[int] = Query(None),
    include_busy: bool = Query(False),
    db: Session = Depends(get_db),
):
    is_admin = patient_id == 0
    if include_busy and not is_admin:
        return error_response(403, "forbidden", "include_busy is only available for admin.")

    try:
        tf = datetime.fromisoformat(time_from)
        tt = datetime.fromisoformat(time_to)
    except ValueError:
        return error_response(400, "invalid_request", "Invalid datetime format. Use ISO 8601.")

    if type == "doctor":
        items = search_doctor_slots(
            db, tf, tt,
            district=district,
            clinic_id=clinic_id,
            direction_id=direction_id,
            doctor_name=doctor_name,
            include_busy=include_busy,
            is_admin=is_admin,
        )
    else:
        items = search_service_slots(
            db, tf, tt,
            district=district,
            clinic_id=clinic_id,
            service_id=service_id,
            include_busy=include_busy,
            is_admin=is_admin,
        )

    return {"items": items}


# ---------------------------------------------------------------------------
# Visits
# ---------------------------------------------------------------------------
@app.post("/api/v1/visits", response_model=BookVisitResponse, tags=["Visits"])
def api_book_visit(
    body: BookVisitRequest,
    patient_id: int = Query(...),
    db: Session = Depends(get_db),
):
    if patient_id <= 0:
        return error_response(400, "invalid_request", "patient_id must be > 0 for booking.")

    try:
        start_dt = datetime.fromisoformat(body.start)
    except ValueError:
        return error_response(400, "invalid_request", "Invalid datetime format.")

    visit_id, err = book_visit(
        db,
        patient_id=patient_id,
        visit_type=body.visit_type.value,
        doctor_id=body.doctor_id,
        service_id=body.service_id,
        clinic_id=body.clinic_id,
        start=start_dt,
    )
    if err:
        code_map = {
            "invalid_request": 400,
            "not_found": 404,
            "slot_busy": 409,
            "not_in_schedule": 409,
        }
        return error_response(code_map.get(err, 500), err, f"Booking failed: {err}")

    return {"visit_id": visit_id, "status": "booked"}


@app.get("/api/v1/visits", response_model=VisitListResponse, tags=["Visits"])
def api_list_visits(
    patient_id: int = Query(...),
    time_from: Optional[str] = Query(None),
    time_to: Optional[str] = Query(None),
    scope: str = Query("mine"),
    db: Session = Depends(get_db),
):
    is_admin = patient_id == 0

    if scope == "all" and not is_admin:
        return error_response(403, "forbidden", "scope=all is only available for admin.")

    now = datetime.now()
    try:
        tf = datetime.fromisoformat(time_from) if time_from else now
        tt = datetime.fromisoformat(time_to) if time_to else now + timedelta(days=90)
    except ValueError:
        return error_response(400, "invalid_request", "Invalid datetime format.")

    q = db.query(Visit).filter(
        Visit.start_datetime >= tf,
        Visit.start_datetime <= tt,
    )
    if scope != "all":
        q = q.filter(Visit.patient_id == patient_id)

    visits = q.order_by(Visit.start_datetime).all()

    items = []
    for v in visits:
        doc_name = None
        svc_name = None
        if v.doctor:
            doc_name = _doctor_name(v.doctor)
        if v.service:
            svc_name = v.service.name
        end_dt = v.start_datetime + timedelta(minutes=v.duration_minutes)
        items.append(VisitItem(
            visit_id=v.id,
            patient_id=v.patient_id,
            visit_type=v.visit_type,
            clinic_id=v.clinic_id,
            clinic_name=v.clinic.name,
            doctor_id=v.doctor_id,
            doctor_name=doc_name,
            service_id=v.service_id,
            service_name=svc_name,
            start=v.start_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
            end=end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        ))

    return {"items": items}


@app.delete("/api/v1/visits/{visit_id}", response_model=DeleteResponse, tags=["Visits"])
def api_cancel_visit(
    visit_id: int,
    patient_id: int = Query(...),
    db: Session = Depends(get_db),
):
    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    if not visit:
        return error_response(404, "not_found", "Visit not found.")

    is_admin = patient_id == 0
    if not is_admin and visit.patient_id != patient_id:
        return error_response(403, "forbidden", "You can only cancel your own visits.")

    db.delete(visit)
    db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Web UI pages
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def page_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/search", response_class=HTMLResponse, include_in_schema=False)
def page_search(request: Request, db: Session = Depends(get_db)):
    clinics = db.query(Clinic).order_by(Clinic.name).all()
    directions = db.query(Direction).order_by(Direction.name).all()
    services = db.query(Service).order_by(Service.name).all()
    districts = sorted(set(c.district for c in clinics))
    return templates.TemplateResponse("search.html", {
        "request": request,
        "clinics": clinics,
        "directions": directions,
        "services": services,
        "districts": districts,
    })


@app.get("/visits", response_class=HTMLResponse, include_in_schema=False)
def page_visits(request: Request):
    return templates.TemplateResponse("visits.html", {"request": request})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=APP_PORT, reload=False)
