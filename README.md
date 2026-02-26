# Family Health - Visit Scheduling Module (Demo)

Demo scheduling service for the fictional clinic network **Family Health**.

## Quick Start

```bash
docker compose up --build
```

- **Web UI**: http://localhost:8080
- **Swagger UI**: http://localhost:8080/docs
- **OpenAPI JSON**: http://localhost:8080/openapi.json

On first startup, MySQL is initialized with schema and seed data (3 clinics, 10 doctors, 6 services, 14 days of schedules).

## Features

- **Slot Search** — filter by type (doctor/service), district, clinic, direction, date range
- **Booking** — book free slots with overlap and schedule validation
- **Visit Management** — list and cancel visits
- **Admin Mode** — set Patient ID = 0 to see all visits, busy slots with patient IDs
- **REST API** — full JSON API at `/api/v1/`

## Project Structure

```
├── docker-compose.yml
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py            # FastAPI application
│   ├── config.py           # Environment config
│   ├── database.py         # DB connection with retry
│   ├── models.py           # SQLAlchemy models
│   ├── schemas.py          # Pydantic schemas
│   ├── slot_service.py     # Slot generation & booking logic
│   └── templates/          # Jinja2 HTML templates
├── db/init/
│   ├── 01_schema.sql       # Table definitions
│   └── 02_seed.sql         # Demo data
└── photos/                 # Optional doctor photos volume
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/slots/search` | Search available slots |
| POST | `/api/v1/visits` | Book a visit |
| GET | `/api/v1/visits` | List visits |
| DELETE | `/api/v1/visits/{id}` | Cancel a visit |
| GET | `/api/v1/clinics` | List clinics |
| GET | `/api/v1/directions` | List directions |
| GET | `/api/v1/doctors` | List doctors |
| GET | `/api/v1/services` | List services |

All endpoints require `patient_id` query parameter. Use `patient_id=0` for admin access.

## Persistence

MySQL data persists in the `fh_mysql_data` Docker volume. To reset:

```bash
docker compose down -v
docker compose up --build
```
