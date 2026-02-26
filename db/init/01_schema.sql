-- Family Health Demo: Schema
-- Executed on first MySQL container startup

CREATE TABLE IF NOT EXISTS clinic (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    district    VARCHAR(100) NOT NULL,
    address     VARCHAR(300) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS direction (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS doctor (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    first_name       VARCHAR(100) NOT NULL,
    last_name        VARCHAR(100) NOT NULL,
    middle_name      VARCHAR(100) DEFAULT NULL,
    bio_text         TEXT,
    photo_path       VARCHAR(300) DEFAULT NULL,
    duration_minutes INT NOT NULL DEFAULT 30,
    buffer_minutes   INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS doctor_direction (
    doctor_id    INT NOT NULL,
    direction_id INT NOT NULL,
    PRIMARY KEY (doctor_id, direction_id),
    FOREIGN KEY (doctor_id) REFERENCES doctor(id),
    FOREIGN KEY (direction_id) REFERENCES direction(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS service (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(200) NOT NULL,
    clinic_id        INT NOT NULL,
    duration_minutes INT NOT NULL DEFAULT 30,
    buffer_minutes   INT NOT NULL DEFAULT 0,
    FOREIGN KEY (clinic_id) REFERENCES clinic(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS doctor_schedule (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    doctor_id  INT NOT NULL,
    clinic_id  INT NOT NULL,
    work_date  DATE NOT NULL,
    time_start TIME NOT NULL,
    time_end   TIME NOT NULL,
    FOREIGN KEY (doctor_id) REFERENCES doctor(id),
    FOREIGN KEY (clinic_id) REFERENCES clinic(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS service_schedule (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    service_id INT NOT NULL,
    work_date  DATE NOT NULL,
    time_start TIME NOT NULL,
    time_end   TIME NOT NULL,
    FOREIGN KEY (service_id) REFERENCES service(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS visit (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    patient_id       INT NOT NULL,
    visit_type       ENUM('DOCTOR','SERVICE') NOT NULL,
    doctor_id        INT DEFAULT NULL,
    service_id       INT DEFAULT NULL,
    clinic_id        INT NOT NULL,
    start_datetime   DATETIME NOT NULL,
    duration_minutes INT NOT NULL,
    buffer_minutes   INT NOT NULL DEFAULT 0,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (doctor_id) REFERENCES doctor(id),
    FOREIGN KEY (service_id) REFERENCES service(id),
    FOREIGN KEY (clinic_id) REFERENCES clinic(id),
    -- Uniqueness: one resource + start time can only be booked once
    UNIQUE KEY uq_doctor_visit (doctor_id, start_datetime),
    UNIQUE KEY uq_service_visit (service_id, start_datetime)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
