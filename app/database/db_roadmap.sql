CREATE TABLE roadmaps (
    roadmapid INTEGER PRIMARY KEY,
    studentid INTEGER,
    target_score NUMERIC(5,2),
    study_timeframe VARCHAR(255),
    generated_plan JSON,
    created_at TIMESTAMP(6),

    CONSTRAINT fk_student
        FOREIGN KEY (studentid)
        REFERENCES students(studentid)
        ON DELETE CASCADE
);