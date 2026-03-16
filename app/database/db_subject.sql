CREATE TABLE subjects (
    subject_id SERIAL PRIMARY KEY,
    subject_name VARCHAR(100),
    created_at TIMESTAMP(6),
    updated_at TIMESTAMP(6)
);