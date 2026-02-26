-- Family Health Demo: Seed Data
-- Provides demo dataset for immediate use after first startup

-- ============================================================
-- Clinics (3 clinics, 2 districts)
-- ============================================================
INSERT INTO clinic (id, name, district, address) VALUES
(1, 'Family Health Mitte',    'Mitte',        'Friedrichstr. 100, Berlin'),
(2, 'Family Health West',     'Charlottenburg','Kantstr. 42, Berlin'),
(3, 'Family Health Pankow',   'Pankow',       'Breite Str. 15, Berlin');

-- ============================================================
-- Directions (medical specialties)
-- ============================================================
INSERT INTO direction (id, name) VALUES
(1, 'Therapist'),
(2, 'Cardiologist'),
(3, 'Neurologist'),
(4, 'Dermatologist'),
(5, 'Pediatrician'),
(6, 'ENT Specialist');

-- ============================================================
-- Doctors (10 doctors)
-- ============================================================
INSERT INTO doctor (id, first_name, last_name, middle_name, bio_text, photo_path, duration_minutes, buffer_minutes) VALUES
(1,  'Ivan',    'Ivanov',    'Petrovich',   '15 years of experience in general practice. Specializes in preventive medicine and chronic disease management.', NULL, 30, 5),
(2,  'Maria',   'Petrova',   NULL,          'Board-certified cardiologist with expertise in echocardiography and heart failure management.', NULL, 40, 10),
(3,  'Alexei',  'Smirnov',   'Dmitrievich', 'Experienced therapist and cardiologist. Published researcher in cardiovascular prevention.', NULL, 30, 5),
(4,  'Elena',   'Kozlova',   NULL,          'Neurologist specializing in headache disorders, epilepsy, and neurorehabilitation.', NULL, 45, 10),
(5,  'Dmitri',  'Volkov',    'Sergeevich',  'Dermatologist with 10 years experience. Expert in allergic skin conditions and cosmetic dermatology.', NULL, 20, 5),
(6,  'Olga',    'Novikova',  NULL,          'Pediatrician with a gentle approach. Experienced in newborn care and childhood vaccinations.', NULL, 30, 5),
(7,  'Sergei',  'Morozov',   'Ivanovich',   'ENT specialist. Performs diagnostic endoscopy and treats chronic sinusitis and hearing disorders.', NULL, 25, 5),
(8,  'Anna',    'Fedorova',  NULL,          'Therapist focused on elderly care and management of diabetes and hypertension.', NULL, 30, 5),
(9,  'Pavel',   'Sokolov',   'Andreevich',  'Cardiologist specializing in arrhythmia management and cardiac rehabilitation.', NULL, 40, 10),
(10, 'Natalia', 'Lebedeva',  NULL,          'Pediatrician and neurologist. Focuses on child development disorders and pediatric neurology.', NULL, 35, 10);

-- ============================================================
-- Doctor-Direction mapping
-- ============================================================
INSERT INTO doctor_direction (doctor_id, direction_id) VALUES
-- Ivanov: Therapist
(1, 1),
-- Petrova: Cardiologist
(2, 2),
-- Smirnov: Therapist + Cardiologist
(3, 1), (3, 2),
-- Kozlova: Neurologist
(4, 3),
-- Volkov: Dermatologist
(5, 4),
-- Novikova: Pediatrician
(6, 5),
-- Morozov: ENT Specialist
(7, 6),
-- Fedorova: Therapist
(8, 1),
-- Sokolov: Cardiologist
(9, 2),
-- Lebedeva: Pediatrician + Neurologist
(10, 5), (10, 3);

-- ============================================================
-- Services (6 services across clinics)
-- ============================================================
INSERT INTO service (id, name, clinic_id, duration_minutes, buffer_minutes) VALUES
(1, 'Blood Test (Labs)',  1, 15, 5),
(2, 'Ultrasound',         1, 30, 10),
(3, 'MRI',                2, 45, 15),
(4, 'CT Scan',            2, 30, 15),
(5, 'X-Ray',              3, 15, 5),
(6, 'ECG',                3, 20, 5);

-- ============================================================
-- Doctor Schedules (next 14 days generated via procedure)
-- We use a stored procedure to generate dates dynamically
-- ============================================================
DELIMITER //
CREATE PROCEDURE seed_schedules()
BEGIN
    DECLARE d INT DEFAULT 0;
    DECLARE cur_date DATE;

    WHILE d < 14 DO
        SET cur_date = DATE_ADD(CURDATE(), INTERVAL d DAY);

        -- Skip Sundays (DAYOFWEEK: 1=Sunday)
        IF DAYOFWEEK(cur_date) != 1 THEN

            -- Ivanov @ Mitte, Mon-Sat
            INSERT INTO doctor_schedule (doctor_id, clinic_id, work_date, time_start, time_end)
            VALUES (1, 1, cur_date, '09:00', '17:00');

            -- Petrova @ Mitte, Mon-Fri
            IF DAYOFWEEK(cur_date) NOT IN (1, 7) THEN
                INSERT INTO doctor_schedule (doctor_id, clinic_id, work_date, time_start, time_end)
                VALUES (2, 1, cur_date, '10:00', '18:00');
            END IF;

            -- Smirnov @ West, Mon-Fri
            IF DAYOFWEEK(cur_date) NOT IN (1, 7) THEN
                INSERT INTO doctor_schedule (doctor_id, clinic_id, work_date, time_start, time_end)
                VALUES (3, 2, cur_date, '08:00', '16:00');
            END IF;

            -- Kozlova @ Pankow, Mon-Fri
            IF DAYOFWEEK(cur_date) NOT IN (1, 7) THEN
                INSERT INTO doctor_schedule (doctor_id, clinic_id, work_date, time_start, time_end)
                VALUES (4, 3, cur_date, '09:00', '15:00');
            END IF;

            -- Volkov @ Mitte, Mon/Wed/Fri
            IF DAYOFWEEK(cur_date) IN (2, 4, 6) THEN
                INSERT INTO doctor_schedule (doctor_id, clinic_id, work_date, time_start, time_end)
                VALUES (5, 1, cur_date, '10:00', '14:00');
            END IF;

            -- Novikova @ Pankow, Mon-Sat
            INSERT INTO doctor_schedule (doctor_id, clinic_id, work_date, time_start, time_end)
            VALUES (6, 3, cur_date, '08:00', '14:00');

            -- Morozov @ West, Tue/Thu
            IF DAYOFWEEK(cur_date) IN (3, 5) THEN
                INSERT INTO doctor_schedule (doctor_id, clinic_id, work_date, time_start, time_end)
                VALUES (7, 2, cur_date, '09:00', '17:00');
            END IF;

            -- Fedorova @ West, Mon-Fri
            IF DAYOFWEEK(cur_date) NOT IN (1, 7) THEN
                INSERT INTO doctor_schedule (doctor_id, clinic_id, work_date, time_start, time_end)
                VALUES (8, 2, cur_date, '08:00', '16:00');
            END IF;

            -- Sokolov @ Mitte, Mon-Fri
            IF DAYOFWEEK(cur_date) NOT IN (1, 7) THEN
                INSERT INTO doctor_schedule (doctor_id, clinic_id, work_date, time_start, time_end)
                VALUES (9, 1, cur_date, '11:00', '19:00');
            END IF;

            -- Lebedeva @ Pankow, Mon/Wed/Fri
            IF DAYOFWEEK(cur_date) IN (2, 4, 6) THEN
                INSERT INTO doctor_schedule (doctor_id, clinic_id, work_date, time_start, time_end)
                VALUES (10, 3, cur_date, '09:00', '15:00');
            END IF;

            -- Service schedules (all Mon-Sat where applicable)

            -- Blood Test @ Mitte
            INSERT INTO service_schedule (service_id, work_date, time_start, time_end)
            VALUES (1, cur_date, '07:00', '12:00');

            -- Ultrasound @ Mitte, Mon-Fri
            IF DAYOFWEEK(cur_date) NOT IN (1, 7) THEN
                INSERT INTO service_schedule (service_id, work_date, time_start, time_end)
                VALUES (2, cur_date, '08:00', '17:00');
            END IF;

            -- MRI @ West, Mon-Fri
            IF DAYOFWEEK(cur_date) NOT IN (1, 7) THEN
                INSERT INTO service_schedule (service_id, work_date, time_start, time_end)
                VALUES (3, cur_date, '08:00', '20:00');
            END IF;

            -- CT Scan @ West, Mon-Fri
            IF DAYOFWEEK(cur_date) NOT IN (1, 7) THEN
                INSERT INTO service_schedule (service_id, work_date, time_start, time_end)
                VALUES (4, cur_date, '08:00', '18:00');
            END IF;

            -- X-Ray @ Pankow
            INSERT INTO service_schedule (service_id, work_date, time_start, time_end)
            VALUES (5, cur_date, '08:00', '16:00');

            -- ECG @ Pankow, Mon-Fri
            IF DAYOFWEEK(cur_date) NOT IN (1, 7) THEN
                INSERT INTO service_schedule (service_id, work_date, time_start, time_end)
                VALUES (6, cur_date, '09:00', '15:00');
            END IF;

        END IF;

        SET d = d + 1;
    END WHILE;
END //
DELIMITER ;

CALL seed_schedules();
DROP PROCEDURE IF EXISTS seed_schedules;

-- ============================================================
-- Pre-booked visits (for admin demo)
-- These reference tomorrow's date so they are always "future"
-- ============================================================
INSERT INTO visit (patient_id, visit_type, doctor_id, service_id, clinic_id, start_datetime, duration_minutes, buffer_minutes)
SELECT 777, 'DOCTOR', 1, NULL, 1,
       TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 1 DAY), '10:00:00'), 30, 5
FROM dual
WHERE DAYOFWEEK(DATE_ADD(CURDATE(), INTERVAL 1 DAY)) NOT IN (1);

INSERT INTO visit (patient_id, visit_type, doctor_id, service_id, clinic_id, start_datetime, duration_minutes, buffer_minutes)
SELECT 777, 'SERVICE', NULL, 3, 2,
       TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 2 DAY), '09:00:00'), 45, 15
FROM dual
WHERE DAYOFWEEK(DATE_ADD(CURDATE(), INTERVAL 2 DAY)) NOT IN (1);

INSERT INTO visit (patient_id, visit_type, doctor_id, service_id, clinic_id, start_datetime, duration_minutes, buffer_minutes)
SELECT 100, 'DOCTOR', 2, NULL, 1,
       TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 1 DAY), '11:00:00'), 40, 10
FROM dual
WHERE DAYOFWEEK(DATE_ADD(CURDATE(), INTERVAL 1 DAY)) NOT IN (1);

INSERT INTO visit (patient_id, visit_type, doctor_id, service_id, clinic_id, start_datetime, duration_minutes, buffer_minutes)
SELECT 200, 'SERVICE', NULL, 1, 1,
       TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 3 DAY), '08:00:00'), 15, 5
FROM dual
WHERE DAYOFWEEK(DATE_ADD(CURDATE(), INTERVAL 3 DAY)) NOT IN (1);
